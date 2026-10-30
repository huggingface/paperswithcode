# Private LaTeX compiler staging runbook

The LaTeX compiler is a staging-only, disabled-by-default boundary for
untrusted manuscript bundles. It is not a public API and it must never receive
PwC database, artifact-bucket, model-provider, user, or signing-private-key
credentials.

## Current qualification decision

**Do not enable paper compilation until qualification passes.** The per-job
Modal sandbox deployment is unqualified, so
`PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED=false` is the required staging state.

History:

- 2026-08-25: a long-lived Docker Space was rejected. It did not establish a
  per-job network boundary, so a compiler compromise could have sent a
  manuscript elsewhere. Serialized execution did not solve this.
- 2026-10-13: per-job Hugging Face Sandbox jobs were replaced by Modal
  sandboxes. Each HF job re-pulled the 2.5 GB TeX Live image, so a compile took
  about 160 s from submission (152–158 s of it scheduling) against about 10 s
  for a small image. That broke the AI repair budget. With the same image,
  Modal started a cached, network-blocked sandbox in 0.1 s and returned a
  compiled PDF 5–13 s after creation.

`backend/services/latex_compiler_service.py` creates one dedicated Modal
sandbox per immutable source version in the `pwc-latex-staging` environment.
The sandbox:

- has all networking blocked by Modal (`block_network=True`);
- receives no secrets or volumes, only the compiler's public signing key;
- runs every process as the image's unprivileged `compiler` user, because Modal
  ignores the image's `USER`;
- starts the compiler only after a fresh user/network/PID namespace proves it
  has no default route and the 96 MB tmpfs workspace quota holds. If that
  preflight fails, the submission fails before any manuscript bytes are sent.

The backend reaches the compiler's loopback API by running
`latex_compiler_space.local_client` with `Sandbox.exec`, so no inbound port or
tunnel is opened.

## Publishing the compiler image

Create the Modal environment once, then build the image from the checked-in
`latex_compiler_space/` and print its immutable ID:

```bash
modal environment create pwc-latex-staging
uv run python -m backend.scripts.publish_latex_compiler_image
```

Rebuild and re-qualify whenever `latex_compiler_space/` or
`latex_compiler_contract/` changes; qualification evidence is bound to one
image ID.

## Guarded staging configuration

Do not edit compiler pins, the signing key or paper gates directly in
`staging.env`. First create a root-owned, mode-`0600` source file outside the
checkout containing exactly these values:

```text
PWC_CHAT_LATEX_COMPILER_MODAL_IMAGE_ID=<im-... from the publish script>
PWC_CHAT_LATEX_COMPILER_MODAL_ENVIRONMENT=pwc-latex-staging
PWC_CHAT_LATEX_COMPILER_SIGNING_PRIVATE_KEY=<base64url-ed25519-private-key>
```

The compiler has no credential of its own. The backend creates its sandboxes
with the staging Modal workspace credential (`MODAL_TOKEN_ID` and
`MODAL_TOKEN_SECRET`), which the transitions below require.

Install the validated pins and credentials with every user and qualification
gate off:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env /root/protected/staging-latex-paper.env \
  --staging-latex-paper-install-only \
  --confirm INSTALL_STAGING_LATEX_PAPER
```

After the exact image has been published and approved, arm only
the qualification path. This keeps `/write-paper`, agent-created paper
artifacts, and compiler job submission unavailable to users:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/staging.env \
  --staging-latex-paper-qualification-enable-only \
  --confirm ENABLE_STAGING_LATEX_PAPER_QUALIFICATION
```

Deploy that exact source commit to staging, run the qualification suite below,
and inspect its root-owned evidence. Compiler qualification submits jobs
directly and does not route chat turns, so it can run while staging chat uses
external Pi.

Paper turns run only on the Modal sandbox worker. External Pi admission accepts
ordinary research, so the backend refuses to boot with paper flags and
`PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED=true`, and activation refuses to write
that combination. Before activation, move staging chat back to the sandbox
worker:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/staging.env \
  --staging-external-pi-disable-only \
  --confirm DISABLE_STAGING_EXTERNAL_PI
```

This turns admission off together with every switch that requires it (the
remote executor transport, remote workspace tools, the safe CLI fast path and
lazy workspaces) and restores the sandbox-worker pool, prewarm and concurrency
baseline. It first saves the exact prior value of each key it changes to the
root-only `/etc/paperswithcode/staging-external-pi-profile.env`. Deploy staging
and confirm ordinary chat works on the sandbox worker before activating papers.

The pinned staging chat image (`PWC_CHAT_MODAL_IMAGE_VERSION`) must bake the
current `paper_cli.py` and paper guides; republish and repin it when either
changes. External Pi admission stays off while papers are enabled. After the
paper disable transition below, restore the saved external Pi profile and
deploy staging:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/staging.env \
  --staging-external-pi-enable-only \
  --confirm ENABLE_STAGING_EXTERNAL_PI
```

The enable transition refuses to run while either paper gate is on.

Only after every required check passes may an operator configure the coherent
user-facing state and deploy staging again:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/staging.env \
  --staging-latex-paper-activation-enable-only \
  --confirm ENABLE_STAGING_LATEX_PAPER
```

Activation remains fail-closed when the qualification evidence is absent,
incomplete, for another image ID, or has unsafe ownership or permissions.
Each command changes protected configuration only; it does not restart or
deploy a service.

## Kill switch

To stop all **new** compiler submissions while preserving owner reads of stored
source and historical PDFs, run the guarded disable transition:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/staging.env \
  --staging-latex-paper-disable-only \
  --confirm DISABLE_STAGING_LATEX_PAPER
```

Then deploy staging. This atomically restores both paper gates and qualification
mode to false while leaving Posterly and shared previews disabled. It does not
delete artifacts or invalidate safe historical previews.

## Health and metrics

Each disposable sandbox exposes only content-free operational endpoints on its
loopback interface, reached through `Sandbox.exec`:

- `GET /health` reports readiness, serialized capacity, queue depth, active
  work, retained-job count, outcome totals, failure-category totals, and a
  bounded latency sample.
- `GET /metrics` returns the same bounded counters for collection.

No endpoint, application log, or metric contains a job ID, source digest,
manuscript bytes, diagnostics, signed envelope, provider handle, or credential.
Uvicorn access logs are disabled. The backend logs only `sandbox_ready` and
`sandbox_released` event names.

Alert on non-zero or rising `timeout`, `resource_limit`, `execution_error`,
`service_error`, `transport_failure`, or `lost` counts; alert immediately when
readiness fails or queue depth remains non-zero without active work.

## Restart and reconciliation

Each immutable paper version uses its UUID as its compiler idempotency key. Its
pending diagnostics persist the opaque Modal sandbox ID. After a backend
restart reconciliation first reattaches with `Sandbox.from_id`; if the sandbox
has already ended, it creates one replacement sandbox with the same source archive,
root document, digest, and logical idempotency key. It cannot create a second
logical version. Terminal result read or cancellation always terminates the
dedicated sandbox; repeated cancellation is idempotent.

After confirming the compiler is enabled and healthy, an operator can process
at most 100 pending versions at a time:

```bash
uv run --env-file /etc/paperswithcode/staging.env \
  python -m backend.scripts.reconcile_latex_compiler_jobs \
  --limit 20 --confirm RECONCILE_STAGING_LATEX_COMPILER_JOBS
```

The command refuses non-staging environments and an enabled kill switch. It
prints only `{"reconciled": N}`. A missing/corrupt durable source archive is
marked `lost`; a temporary transport fault remains queued for a later bounded
retry. Do not retry a failed qualification by changing a manuscript or its
digest under the same version ID.

When the compiler kill switch is on, an operator may append `--cleanup-only`
to reclaim the bounded queue of already-unreachable private storage prefixes;
this mode never submits or resumes compiler work.

## Qualification procedure

Only after the exact external inputs above are supplied and the kill switch is
intentionally enabled for this isolated staging exercise:

```bash
uv run --env-file /etc/paperswithcode/staging.env \
  python -m backend.scripts.qualify_latex_compiler_sandbox \
  --confirm QUALIFY_PRIVATE_LATEX_COMPILER_SANDBOX
```

The suite uses fixed synthetic bundles for shell escape, host file reads,
network pipe input, recursive expansion, process pressure, oversized output,
path traversal, malformed archives, and malformed PDF figures. It prints only
case names, terminal outcomes, and elapsed milliseconds. Also perform one
manual cancellation while compiling and one controlled Sandbox/backend restart
followed by the reconciliation command; record `/health` and `/metrics` before
and after. Confirm that the isolation preflight completed before submitting the
first fixture, that each sandbox had networking blocked and no secrets or
volumes, and that each terminal fixture terminated its dedicated sandbox. Keep
all manuscript content out of tickets, terminal capture, and provider logs.

Passing local contract tests does **not** qualify the remote isolation. Do not
claim this procedure passed until the exact image ID and environment have been
configured and the isolated runtime has actually run it successfully.

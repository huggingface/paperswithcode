# Private LaTeX compiler staging runbook

The LaTeX compiler is a staging-only, disabled-by-default boundary for
untrusted manuscript bundles. It is not a public API and it must never receive
PwC database, artifact-bucket, model-provider, user, or signing-private-key
credentials.

## Current qualification decision

**Do not enable paper compilation.** The per-job Sandbox deployment remains
unqualified, so `PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED=false` is the required
staging state.

Evidence captured on 2026-08-25:

- The authenticated Hub identity is `nielsr`, but `hf spaces list --author
  nielsr --search pwc` returned only public curator Spaces; no existing private
  compiler Space was available to inspect.
- The then-current staging example left the compiler URL, private-Space token,
  and signing key empty, so no endpoint was available for a live request.
- The compiler image ran as an unprivileged user with a minimal environment and
  no application credentials, but the rejected long-lived Docker Space
  deployment did not establish a per-job network boundary. A compiler
  compromise could have made outbound requests with the manuscript it received.
  Serialized execution did not solve this confidentiality risk.

Consequently, a long-lived Docker Space is not adequate evidence for the
privacy boundary. The application factory now selects only the per-job Hugging
Face Sandbox transport in `backend/services/latex_compiler_service.py`. It
creates one dedicated HF Job VM for each immutable source version, does not
forward the backend HF token, mounts no volumes or secrets, injects only the
compiler's public signing key, and starts the compiler only after a fresh,
unprivileged user/network/PID namespace has no default route. If that preflight
cannot run, the submission fails before any manuscript bytes are sent.

The rejected long-lived Docker Space deployment, direct HTTP client, deployment
script, and Space-specific settings have been removed. The compiler image under
`latex_compiler_space/` is retained only as the OCI runtime launched inside each
per-job Sandbox.

The required external staging inputs remain intentionally blank in the release
example: an operator-approved private namespace, an immutable compiler image
digest, a protected Sandbox-only credential, and the exact
`sandbox-netns-v1` egress-policy attestation. Do not derive these from the
authenticated developer identity, reuse an unrelated credential, or invent a
target.

## Guarded staging configuration

Do not edit compiler secrets or paper gates directly in `staging.env`. First
create a root-owned, mode-`0600` source file outside the checkout containing
exactly the approved values below. Keep the Sandbox credential distinct from
`PWC_HF_TOKEN`.

```text
PWC_CHAT_LATEX_COMPILER_HF_SANDBOX_IMAGE=registry.hf.space/nielsr-pwc-latex-compiler-<private-name>-staging@sha256:<digest>
PWC_CHAT_LATEX_COMPILER_HF_SANDBOX_NAMESPACE=nielsr
PWC_CHAT_LATEX_COMPILER_HF_SANDBOX_TOKEN=<sandbox-only-token>
PWC_CHAT_LATEX_COMPILER_HF_SANDBOX_FLAVOR=cpu-upgrade
PWC_CHAT_LATEX_COMPILER_HF_SANDBOX_IDLE_TIMEOUT_SECONDS=180
PWC_CHAT_LATEX_COMPILER_HF_SANDBOX_EGRESS_POLICY_ATTESTATION=sandbox-netns-v1
PWC_CHAT_LATEX_COMPILER_SIGNING_PRIVATE_KEY=<base64url-ed25519-private-key>
```

Install the validated pins and credentials with every user and qualification
gate off:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env /root/protected/staging-latex-paper.env \
  --staging-latex-paper-install-only \
  --confirm INSTALL_STAGING_LATEX_PAPER
```

After the exact private image and Sandbox boundary have been approved, arm only
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
worker: set external Pi admission off, and confirm the pinned staging Modal
image (`PWC_CHAT_MODAL_IMAGE_VERSION`) was published from a commit that bakes
the current `paper_cli.py` and paper guides. Republish and repin the image if
either file changed since it was built. External Pi admission stays off while
papers are enabled; re-enable it only after the disable transition below.

Only after every required check passes may an operator configure the coherent
user-facing state and deploy staging again:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/staging.env \
  --staging-latex-paper-activation-enable-only \
  --confirm ENABLE_STAGING_LATEX_PAPER
```

Activation remains fail-closed when the qualification evidence is absent,
incomplete, for another image digest, or has unsafe ownership or permissions.
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

Each disposable Sandbox exposes only content-free operational endpoints through
its short-lived, authenticated Sandbox proxy:

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
pending diagnostics persist the opaque Sandbox job handle. After a backend
restart reconciliation first reconnects with `Sandbox.connect`; if the VM has
already ended, it creates one replacement Sandbox with the same source archive,
root document, digest, and logical idempotency key. It cannot create a second
logical version. Terminal result read or cancellation always kills the
dedicated Sandbox; repeated cancellation is idempotent.

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
and after. Confirm that the Sandbox preflight completed before submitting the
first fixture, that the provider Job has no forwarded HF token, mounts, or
secrets, and that each terminal fixture releases its dedicated Job. Keep all
manuscript content out of tickets, terminal capture, and provider logs.

Passing local contract tests does **not** qualify the remote isolation. Do not
claim this procedure passed until the exact private namespace/image/credential
and egress attestation have been configured and the isolated runtime has
actually run it successfully.

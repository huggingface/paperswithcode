# Private LaTeX compiler staging runbook

The LaTeX compiler is a staging-only, disabled-by-default boundary for
untrusted manuscript bundles. It is not a public API and it must never receive
PwC database, artifact-bucket, model-provider, user, or signing-private-key
credentials.

## Current qualification decision

**Do not enable paper compilation.** The required steady state until every
gate passes is `PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED=false` and
`PWC_CHAT_LATEX_PAPER_ENABLED=false`.

A long-lived Docker Space is not adequate evidence for the privacy boundary.
The only application transport is the per-job Hugging Face Sandbox client in
`backend/services/latex_compiler_service.py`. It creates one dedicated VM per
immutable source version, does not forward the backend HF token, mounts no
volumes or secrets, injects only a public signing key and the requested
immutable image reference, and starts the compiler only after a fresh,
unprivileged user/network/PID namespace has no default route. If any preflight,
image identity, or network-isolation check fails, no manuscript bytes are sent.

`scripts/deploy_latex_compiler_space.py` may create a private,
clearly-staging-named Docker **image builder**. It waits only to resolve its
authenticated OCI `Docker-Content-Digest`, outputs the non-secret
`registry.hf.space/...@sha256:...` identity, then pauses the Space. The builder
is never a compiler endpoint and must have no secret, variable, volume, or
always-on hardware. Qualification must prove that a fresh Sandbox can pull the
pinned image while that builder remains paused.

The protected staging environment needs an approved private namespace, that
immutable registry image, a Sandbox-only credential, the backend signing
private key, private HF artifact storage, and the exact
`sandbox-netns-v1` egress-policy attestation. Do not reuse a Space endpoint
credential or put any signing key in the builder. The legacy HTTP Space client
remains compatibility-only; `compiler_transport_from_settings` never selects
it. `qualify_latex_compiler_space` intentionally refuses to run.

The only approved compiler owner is `nielsr`. Both the builder and runtime
reject any other owner or an image outside
`registry.hf.space/nielsr-pwc-latex-compiler-*-staging@sha256:<digest>`.

## Kill switch

To stop all **new** compiler submissions while preserving owner reads of stored
source and historical PDFs, set this in `/etc/paperswithcode/staging.env` and
deploy staging:

```text
PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED=false
```

`PWC_CHAT_LATEX_PAPER_ENABLED=false` is the stricter paper-creation switch.
Neither control deletes artifacts or invalidates safe historical previews.

## Isolated qualification mode

Qualification runs with all user-facing artifact, paper, and compiler-job
admission disabled. The protected host configuration may set only the
staging-only qualifier switch alongside the private bucket and immutable
Sandbox contract:

```text
PWC_CHAT_ARTIFACTS_ENABLED=false
PWC_CHAT_ARTIFACT_SHARED_PREVIEW_ENABLED=false
PWC_CHAT_POSTERLY_ENABLED=false
PWC_CHAT_LATEX_PAPER_ENABLED=false
PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED=false
PWC_CHAT_LATEX_COMPILER_QUALIFICATION_MODE=true
```

The qualifier rejects a non-staging environment, a local/non-private artifact
store, missing immutable image identity, or any enabled user-facing artifact,
shared-preview, Posterly, paper, or compiler-job admission. It may send only
its fixed synthetic bundles.

## Health and metrics

Each disposable Sandbox exposes only content-free operational endpoints through
its short-lived, authenticated Sandbox proxy:

- `GET /health` reports readiness, serialized capacity, queue depth, active
  work, retained-job count, outcome totals, failure-category totals, a bounded
  latency sample, the requested immutable image identity, and the
  `sandbox-netns-v1` isolation attestation.
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

Only after the exact external inputs above are supplied and isolated
qualification mode is explicitly enabled (while both user-facing kill switches
remain off):

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --working-directory=/srv/paperswithcode/environments/staging/current \
  --property=EnvironmentFile=/etc/paperswithcode/staging.env \
  --property=UMask=0077 \
  /srv/paperswithcode/.venv/bin/python \
  -m backend.scripts.qualify_latex_compiler_sandbox \
  --confirm QUALIFY_PRIVATE_LATEX_COMPILER_SANDBOX
```

This is intentionally a root unit: do **not** add `--uid=pwc-staging`. The
writer refuses non-root callers, creates the fixed evidence directory as mode
`0700` when absent, and otherwise refuses a linked, non-root-owned, or
group/other-accessible directory. It emits a root-owned regular single-link
mode-`0600` evidence file only.

The full suite uses fixed synthetic bundles for shell escape, host file reads,
network pipe input, recursive expansion, process pressure, CPU, memory, disk,
and output ceilings, path traversal, malformed archives, and malformed PDF
figures. It also checks cancellation, content-free `/health` and `/metrics`,
the exact image/isolation snapshot, and Sandbox reconnect/reconciliation. It
prints only case names, terminal outcomes, and elapsed milliseconds. A complete
passing run atomically writes root-owned, single-link mode-`0600` content-free evidence to
`/var/lib/paperswithcode/staging/latex-compiler-qualification.json`; a full
rerun clears older evidence before it starts, while individual `--case`
fixtures never replace that gate. Confirm independently
that the builder remains paused, provider Jobs have no forwarded HF token,
mounts, or secrets, and every terminal fixture releases its dedicated job.
Keep all manuscript content out of tickets, terminal capture, and provider
logs.

Passing local contract tests does **not** qualify the remote isolation. Do not
claim this procedure passed until the exact private namespace/image/credential
and egress attestation have been configured and the isolated runtime has
actually run it successfully.

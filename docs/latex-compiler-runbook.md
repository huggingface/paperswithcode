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

The required external staging inputs remain intentionally blank in
`deploy/env/staging.env.example` and unset in the protected staging
configuration: an operator-approved private namespace, an immutable compiler
image digest, a protected Sandbox-only credential, and the exact
`sandbox-netns-v1` egress-policy attestation
(`PWC_CHAT_LATEX_COMPILER_HF_SANDBOX_NAMESPACE`, `_IMAGE`, `_TOKEN`,
`_EGRESS_POLICY_ATTESTATION`). Production has no compiler configuration; the
transport and runtime validation refuse any environment other than staging. Do not derive these from the
authenticated developer identity, reuse an unrelated credential, or invent a
target.

## Kill switch

To stop all **new** compiler submissions while preserving owner reads of stored
source and historical PDFs, set this in `/etc/paperswithcode/staging.env` and
deploy staging:

```text
PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED=false
```

`PWC_CHAT_LATEX_PAPER_ENABLED=false` is the stricter paper-creation switch.
Neither control deletes artifacts or invalidates safe historical previews.

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

Only after the exact external inputs above are supplied. The script requires
`PWC_CHAT_LATEX_COMPILER_QUALIFICATION_MODE=true` and refuses to run unless
`PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED`, `PWC_CHAT_LATEX_PAPER_ENABLED`, and all
user-facing artifact features (artifacts, shared previews, Posterly) are
disabled:

```bash
uv run --env-file /etc/paperswithcode/staging.env \
  python -m backend.scripts.qualify_latex_compiler_sandbox \
  --confirm QUALIFY_PRIVATE_LATEX_COMPILER_SANDBOX
```

The suite uses fixed synthetic bundles for shell escape, host file reads,
network pipe input, recursive expansion, process pressure, oversized output,
path traversal, malformed archives, and malformed PDF figures. It prints only
case names, terminal outcomes, and elapsed milliseconds, and writes the same
evidence to
`/var/lib/paperswithcode/staging-compiler-qualification/latex-compiler-qualification.json`
for a full run unless `--no-write-evidence` is passed; `--case <name>` runs
selected cases without writing evidence. Also perform one
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

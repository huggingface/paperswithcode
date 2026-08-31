# PwC LaTeX compiler runtime

This directory builds the OCI runtime launched inside a disposable Hugging Face
Sandbox for each compilation job. It is not a long-lived Docker Space or a
user-facing service. The old Space deployment path was removed because it did
not provide the required per-job isolation and egress boundary.

The runtime accepts only signed compiler envelopes from the PwC backend. It has
no bucket, database, model-provider, user, session, or signing-private-key
credential. The Sandbox injects only:

```text
PWC_LATEX_COMPILER_PUBLIC_KEY=<base64url Ed25519 public key>
```

The matching private key and Sandbox credential belong only in the staging
backend environment. Do not put them in this repository, Sandbox secrets,
image layers, or build logs.

The Dockerfile pins the TeX image by digest. Replacing it requires a reviewed
staging qualification covering the image digest, TeX engine versions, hostile
bundle handling, timeout/cancellation, and the no-network/no-shell-escape
controls. The in-memory queue is intentionally ephemeral: PwC owns durable job
intent and may reconnect to or safely replace a failed per-job Sandbox.

See `docs/latex-compiler-runbook.md` in the PwC source checkout for the
mandatory staging qualification, health/metrics, kill-switch, and restart
reconciliation procedure. Compilation must remain disabled until the exact
Sandbox image and egress boundary have been qualified.

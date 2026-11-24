# PwC LaTeX compiler runtime

This directory builds the OCI runtime launched inside a disposable,
network-blocked Modal sandbox for each compilation job. It is not a long-lived
service or a user-facing API. Build it with
`backend/scripts/publish_latex_compiler_image.py`, which prints the immutable
Modal image ID.

The runtime accepts only signed compiler envelopes from the PwC backend. It has
no bucket, database, model-provider, user, session, or signing-private-key
credential. The sandbox injects only:

```text
PWC_LATEX_COMPILER_PUBLIC_KEY=<base64url Ed25519 public key>
```

The matching private key belongs only in the staging backend environment. Do
not put it in this repository, sandbox secrets, image layers, or build logs.

The compiler API listens on 127.0.0.1 only. The backend reaches it by running
`local_client.py` through `Sandbox.exec`, as the unprivileged `compiler` user.

The Dockerfile pins the TeX image by digest. Replacing it requires a reviewed
staging qualification covering the image, TeX engine versions, hostile bundle
handling, timeout/cancellation, and the no-network/no-shell-escape controls.
The in-memory queue is intentionally ephemeral: PwC owns durable job intent and
may reconnect to or safely replace a failed per-job sandbox.

See `docs/latex-compiler-runbook.md` in the PwC source checkout for the
mandatory staging qualification, health/metrics, kill-switch, and restart
reconciliation procedure. Compilation must remain disabled until the exact
image has been qualified.

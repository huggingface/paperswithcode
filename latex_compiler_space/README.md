---
title: PwC Private LaTeX Compiler
emoji: 📄
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# PwC private LaTeX compiler image builder

This private, staging-only Docker Space is an **image builder**, not a
compiler endpoint. PwC never sends a manuscript to its Space URL. It has no
bucket, database, model-provider, user, session, or signing-private-key
credential, and the provisioning command pauses it after building.

## Private builder setup

Create a **private Docker Space** whose name is
`pwc-latex-compiler-<source>-staging`. From the PwC checkout, assemble the
image and resolve its authenticated OCI manifest digest:

```bash
HF_TOKEN=<private-builder-write-token> uv run python scripts/deploy_latex_compiler_space.py \
  --space <namespace>/pwc-latex-compiler-<source>-staging \
  --confirm DEPLOY_PRIVATE_LATEX_COMPILER_SPACE
```

The command verifies that the Space remains private, waits only long enough to
obtain `Docker-Content-Digest`, prints the non-secret source revision and
immutable `registry.hf.space/...@sha256:...` reference, and pauses the Space in
all post-upload outcomes. Do not request always-on hardware, attach a volume,
or configure any Space secret or variable.

Install the emitted image reference, a protected Sandbox credential, and the
matching backend signing private key only through the staging host’s protected
configuration flow. The backend injects the corresponding public key and the
exact image identity into each fresh Sandbox as non-secret per-job environment
values; neither belongs in the builder Space, image layers, or build logs.

The Dockerfile pins the TeX base image by digest. Replacing it requires a
reviewed staging qualification covering the builder digest, TeX engine
versions, hostile bundles, cancellation, restart/reconciliation, health,
metrics, and the no-network/no-shell-escape controls. Qualification must also
prove that a fresh Sandbox can pull the pinned image while the builder remains
paused. The in-memory queue is intentionally ephemeral: PwC owns durable job
intent and may safely resubmit the same signed job after a backend restart.

See `docs/latex-compiler-runbook.md` in the PwC source checkout for the
mandatory staging qualification, health/metrics, kill-switch, and restart
reconciliation procedure. A Docker Space must remain disabled until its
per-job isolation and egress boundary have been qualified.

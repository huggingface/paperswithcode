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
`pwc-latex-compiler-<source>-staging`. From the already authenticated staging
Hub identity, verify the non-secret account name, then assemble the image and
resolve its authenticated OCI manifest digest. Do not place a token on the
command line, print it, or add it as a Space secret or variable:

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --uid=pwc-staging --gid=pwc-staging \
  --working-directory=/srv/paperswithcode/environments/staging/current \
  --property=EnvironmentFile=/etc/paperswithcode/staging.env \
  /srv/paperswithcode/.venv/bin/python \
  scripts/deploy_latex_compiler_space.py \
  --space <namespace>/pwc-latex-compiler-<source>-staging \
  --verify-identity --confirm DEPLOY_PRIVATE_LATEX_COMPILER_SPACE
```

After the identity-only command returns the approved non-secret account name,
run the same command without `--verify-identity` to build and pause the private
builder. The helper prefers the protected `PWC_HF_TOKEN` made available by the
staging environment and never prints it.

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

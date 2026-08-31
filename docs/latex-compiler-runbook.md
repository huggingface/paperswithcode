# Private LaTeX compiler staging runbook

This is a **staging-only** procedure for untrusted LaTeX bundles. It never
authorizes a production configuration change, migration, deployment, or
compiler run; every compiler action described here is confined to staging.
Keep all paper, artifact, and compiler admission disabled unless the exact
sequence below has passed; if any gate is unavailable, fail closed.

## Required steady state and boundary

The default and rollback state is:

```text
PWC_CHAT_ARTIFACTS_ENABLED=false
PWC_CHAT_ARTIFACT_SHARED_PREVIEW_ENABLED=false
PWC_CHAT_POSTERLY_ENABLED=false
PWC_CHAT_LATEX_PAPER_ENABLED=false
PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED=false
PWC_CHAT_LATEX_COMPILER_QUALIFICATION_MODE=false
```

`PWC_CHAT_POSTERLY_ENABLED` is permanently false for this integration. Do not
use a bridge release or a later configuration refresh to enable it. Existing
immutable private records may remain readable by their owner, but no turn may
create a Posterly artifact or a shareable paper snapshot.

The only compiler transport is the per-job Hugging Face Sandbox client. Each
compile receives a fresh disposable Sandbox pinned to one immutable image. It
does not forward the backend Hub token, mount a volume, or inject a secret; it
passes only the compiler public key, requested image identity, and required
isolation flag. Before accepting a bundle, the Sandbox checks the immutable
image identity, a fresh
`sandbox-netns-v1` network namespace with no default route, and the bounded
tmpfs compiler workspace. If any check fails, no manuscript bytes are sent.

The legacy long-lived Docker Space is not a compiler endpoint. It is only a
private image builder and must have no credential, variable, volume, or
always-on hardware; the builder command pauses it after the image digest is
resolved. Do not set a Space URL or a Space access token as an alternate
compiler path.

The approved staging identity is `nielsr`; the approved private artifact bucket
is `nielsr/pwc-chat-artifacts-staging`. A compiler image must match exactly:

```text
registry.hf.space/nielsr-pwc-latex-compiler-*-staging@sha256:<64-lowercase-hex>
```

The protected staging configuration also requires the exact
`sandbox-netns-v1` egress attestation, `cpu-upgrade` Sandbox flavor, a
180-second idle timeout, a backend-only signing private key, and the existing
authenticated staging Hub credential. The configuration helper installs or
preserves protected values without printing them; neither a token nor a private
key belongs in a command line, an image layer, the builder, a ticket, or logs.

## Exact staging order

Record `pwc-status` before starting: target environment, exact 40-character
source SHA, `current`, and `previous`. Reconcile the target SHA with
`origin/main` before publishing. These steps use only staging release and
configuration paths.

1. Publish the matching Pi/Modal worker image from that source in the existing
   staging Modal identity, pin the emitted immutable `im-...` ID and any
   contract increment in `backend/chat_sandbox_worker/contract.py`, then commit
   and push that source change. The release manifest must name the same image
   and worker contract that contain `pwc-paper`; an application deployment
   cannot change an already-published worker image.
2. Deploy that exact source SHA to **staging** with all six controls above
   false. This installs the builder, runtime validation, qualifier, and guarded
   host-configuration code without admitting a user paper turn:

   ```bash
   sudo pwc-deploy staging <exact-sha>
   ```

3. In the already authenticated staging Hub context, verify only the non-secret
   account name, build a private staging-scoped builder, and retain the emitted
   immutable image reference. Do not run `hf auth token`, print an environment
   file, or supply a token inline. The builder must remain paused when this
   command returns.

   ```bash
   sudo systemd-run --quiet --wait --pipe --collect \
     --uid=pwc-staging --gid=pwc-staging \
     --working-directory=/srv/paperswithcode/environments/staging/current \
     --property=EnvironmentFile=/etc/paperswithcode/staging.env \
     /srv/paperswithcode/.venv/bin/python \
     scripts/deploy_latex_compiler_space.py \
     --space nielsr/pwc-latex-compiler-sandbox-netns-v1-staging \
     --verify-identity --confirm DEPLOY_PRIVATE_LATEX_COMPILER_SPACE

   sudo systemd-run --quiet --wait --pipe --collect \
     --uid=pwc-staging --gid=pwc-staging \
     --working-directory=/srv/paperswithcode/environments/staging/current \
     --property=EnvironmentFile=/etc/paperswithcode/staging.env \
     /srv/paperswithcode/.venv/bin/python \
     scripts/deploy_latex_compiler_space.py \
     --space nielsr/pwc-latex-compiler-sandbox-netns-v1-staging \
     --confirm DEPLOY_PRIVATE_LATEX_COMPILER_SPACE
   ```

   The JSON result contains only the private Space name, source revision, and
   immutable `registry.hf.space/...@sha256:...` reference. Stop here if the
   account is not `nielsr`, the builder is not private/paused, or the result is
   not a digest-pinned staging image.
4. Provision the protected compiler contract while keeping all user-facing
   switches false. Substitute only the non-secret image reference printed in
   the preceding step. The helper reuses the existing protected staging Hub
   identity, keeps it out of every Sandbox, clears the retired direct-Space
   values, and generates or preserves the backend signing key without output.

   ```bash
   sudo /srv/paperswithcode/.venv/bin/python \
     /srv/paperswithcode/environments/staging/current/deploy/configure_host_env.py \
     --legacy-env /etc/paperswithcode/staging.env \
     --staging-latex-compiler-provision-only \
     --staging-latex-compiler-image '<registry-image@sha256:digest>' \
     --confirm PROVISION_PRIVATE_STAGING_LATEX_COMPILER
   sudo pwc-deploy staging <exact-sha> --refresh-environment
   ```

5. Apply the required staging migrations as PostgreSQL superuser, one file at a
   time, with `ON_ERROR_STOP` and `search_path=staging,public`. Never use this
   sequence against `public`. Complete any missing prerequisite migrations in
   [the deployment guide](deployment.md#staging-sandbox-chat-bridge); within
   that sequence, the paper foundation order is:

   1. `add_chat_artifacts.sql`
   2. `expand_chat_artifact_foundation.sql`
   3. `allow_chat_latex_paper_restore_digests.sql`
   4. `add_chat_latex_paper_figure_storage.sql`
   5. `add_chat_latex_repair_provenance.sql`

   For each file, use the deployed release's copy and stop on the first error:

   ```bash
   sudo -u postgres psql --no-psqlrc --set ON_ERROR_STOP=1 \
     --dbname paperswithcode_hf \
     --command 'SET search_path TO staging, public;' \
     --file /srv/paperswithcode/environments/staging/current/backend/database/migrations/<file>.sql
   ```

   Verify the tables, columns, constraints, and ownership are in `staging`; the
   migration scripts grant only `pwc_staging` and revoke the production
   application role. Do not continue if the schema check or staging isolation
   audit fails.
6. Prepare the root-owned qualification-evidence handoff. This narrow action
   changes no service, release pointer, or feature flag:

   ```bash
   sudo /srv/paperswithcode/.venv/bin/python \
     /srv/paperswithcode/environments/staging/current/deploy/configure_host_env.py \
     --legacy-env /etc/paperswithcode/staging.env \
     --staging-latex-compiler-evidence-layout-only \
     --confirm LAYOUT_PRIVATE_STAGING_LATEX_COMPILER_EVIDENCE
   ```

   The directory is exactly
   `/var/lib/paperswithcode/staging-compiler-qualification`, owned
   `root:pwc-staging` mode `0750`. The qualifier is the only root writer; the
   staging service may read but cannot replace the evidence file.
7. Turn on **isolated qualification only**, refresh the same exact staging
   release, and run the fixed synthetic suite as root. All user-facing artifact,
   paper, compiler-job, shared-preview, and Posterly controls remain false.

   ```bash
   sudo /srv/paperswithcode/.venv/bin/python \
     /srv/paperswithcode/environments/staging/current/deploy/configure_host_env.py \
     --legacy-env /etc/paperswithcode/staging.env \
     --staging-latex-compiler-qualification-enable-only \
     --confirm QUALIFY_PRIVATE_STAGING_LATEX_COMPILER
   sudo pwc-deploy staging <exact-sha> --refresh-environment

   sudo systemd-run --quiet --wait --pipe --collect \
     --working-directory=/srv/paperswithcode/environments/staging/current \
     --property=EnvironmentFile=/etc/paperswithcode/staging.env \
     /srv/paperswithcode/.venv/bin/python \
     -m backend.scripts.qualify_latex_compiler_sandbox \
     --confirm QUALIFY_PRIVATE_LATEX_COMPILER_SANDBOX
   ```

   Do **not** add `--uid=pwc-staging` to the qualifier. It writes only a
   content-free JSON verdict at
   `/var/lib/paperswithcode/staging-compiler-qualification/latex-compiler-qualification.json`.
   The file must be a regular, single-link `root:pwc-staging` file mode `0640`,
   at most 16 KiB, bind to the configured immutable image, and contain passing
   `hostile_input`, `cancellation`, `health`, `metrics`, `image_isolation`,
   `restart`, and `reconciliation` checks. A full rerun invalidates old evidence
   before it starts; an individual fixture cannot approve activation.
8. Only after every step above passes, activate paper artifacts and compiler
   jobs through the guarded helper, which atomically disables qualification
   mode and keeps shared previews and Posterly disabled. Then refresh the same
   exact staging SHA.

   ```bash
   sudo /srv/paperswithcode/.venv/bin/python \
     /srv/paperswithcode/environments/staging/current/deploy/configure_host_env.py \
     --legacy-env /etc/paperswithcode/staging.env \
     --staging-latex-paper-enable-only \
     --confirm ENABLE_STAGING_LATEX_PAPER_AFTER_QUALIFICATION
   sudo pwc-deploy staging <exact-sha> --refresh-environment
   ```

   Run the authenticated Luna paper gate, telemetry-content scan, and
   kill-switch historical phase in the deployment guide before treating the
   staging rollout as accepted. Keep the controls off if any external privacy,
   Sandbox isolation, migration, worker-image, or end-to-end gate fails.

## Qualification coverage and observability

The full qualifier sends only fixed synthetic bundles. It covers hostile shell,
host-file, network, archive, recursive-expansion, process, CPU, memory, disk,
and output cases; cancellation; Sandbox restart/reconciliation; `/health`;
`/metrics`; the exact image; no forwarded token, secret, or volume; and the
`sandbox-netns-v1` attestation. A passed local contract test is not evidence of
remote isolation.

`/health` and `/metrics` expose only bounded operational state: readiness,
capacity, queue and active counts, outcome/failure totals, bounded latency,
the requested image identity, egress isolation, and workspace-quota
attestation. They must never contain a manuscript, source digest, diagnostics,
signed envelope, provider handle, token, or key. Treat unexpected readiness,
queue, timeout, resource-limit, transport-failure, or `lost` counts as an
activation failure until investigated without collecting manuscript content.

Each immutable paper version has one logical compiler idempotency key. Pending
diagnostics retain only the opaque Sandbox handle. Reconciliation reconnects
first; it may create one replacement only after the original Sandbox is known
gone, and holds the artifact lock so it cannot duplicate a logical compile.
Terminal read and cancellation release the dedicated Sandbox. A bounded
staging-only reconciliation command is available only while compiler admission
is enabled; it prints aggregate counts only.

## Kill switch and rollback

For an incident, stop new paper and compiler work first; this preserves
owner-only stored source and historical previews:

```bash
sudo /srv/paperswithcode/.venv/bin/python \
  /srv/paperswithcode/environments/staging/current/deploy/configure_host_env.py \
  --legacy-env /etc/paperswithcode/staging.env \
  --staging-latex-paper-disable-only \
  --confirm DISABLE_STAGING_LATEX_PAPER
sudo pwc-deploy staging <exact-sha> --refresh-environment
```

This sets artifact, shared-preview, paper, compiler-job, and qualification
controls false and leaves Posterly false. It is the primary rollback path. If
the source release itself must be restored, inspect `previous` first and use
the supported complete-release rollback only after the kill switch is applied:

```bash
pwc-status
sudo pwc-rollback staging
```

Never recreate a rollback by mixing a frontend and backend, editing a release
directory, restarting a service directly, or touching production. Record the
staging `current`/`previous` release IDs and whether automatic rollback ran.

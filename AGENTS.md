# AGENTS.md

Guidance for agents working in this repository.

## Guardrails

- Production and staging run from immutable releases under
  `/srv/paperswithcode`; treat this checkout as production-adjacent release
  source, never as a runtime directory.
- During routine development, do not restart or stop services, kill processes,
  rebuild/repoint the production frontend, or reload nginx. Deploy only when the
  user explicitly requests a production release.
- Treat approval to implement a repository source change as approval to validate
  it, commit the intended changes directly to `main`, push `origin main`, and
  deploy that exact commit to staging. Do not wait for separate commit, push, or
  staging deployment requests unless the user explicitly asks for local-only
  work or no deployment.
- Preserve public API, route, CLI, and persisted-data contracts. Compatibility is
  optional only for clearly unshipped internal work.
- Keep logic simple and readable; avoid broad defensive `try`/`except` blocks.
- Preserve unrelated work in the dirty tree and edit files narrowly.
- Run Python and repository CLIs with
  `uv run --env-file backend/keys.env …`.
- Follow `docs/database.md` before accessing PostgreSQL.
- Prefer `DBPaper.is_latest_version` to `== True` and
  `~DBPaper.urls_extracted` to `== False`.
- The VPS is resource constrained (about 8 GB RAM / 80 GB disk, with little disk
  headroom). Stream large inputs, use bounded batches, and check capacity first.

## Development

- Put domain logic in `backend/services/`, HTTP adapters in `backend/routers/`,
  API models in `backend/models/api.py`, and persistence models/migrations in
  `backend/models/database.py` and `backend/database/migrations/`.
- Run targeted tests and linters. Do not run the entire suite when a focused check
  is sufficient.
- For an isolated backend, first verify a free non-production port; ports 8000 and
  8001 are currently production/staging and must not be replaced.
- For frontend work, use `npm run dev` and `npm run lint`. Do not run
  `npm run build` as a routine check; it writes `frontend/dist` and consumes scarce
  disk. Keep routes before the catch-all and use `frontend/src/lib/api.ts` plus
  TanStack Query for server state.
- Never reload nginx during development.

## Publishing changes

- After completing and validating a repository source change, commit the
  intended changes directly to `main`, push `origin main`, and deploy the exact
  pushed commit to staging with `pwc-deploy`.
- Read-only investigation and reporting, data-only curation, database operations,
  and other work that does not change deployed source do not require a commit or
  application deployment.
- Do not create a feature branch or pull request unless the user explicitly
  requests one.
- Fetch `origin main` before publishing and never force-push. If local and
  remote `main` have diverged, stop and resolve the divergence safely before
  pushing.
- Staging deployment approval never implies production approval. Do not deploy
  to production unless the user explicitly requests a production release.

## Production releases

Production topology can change, so inspect the active processes and nginx config
before an explicitly authorized release. Currently:

- production is `paperswithcode-backend@production` on `:8000`;
- staging is `paperswithcode-backend@staging` on `:8001`;
- nginx serves each environment's `current/frontend-dist`;
- `pwc-status`, `pwc-deploy`, and `pwc-rollback` are the supported lifecycle
  interfaces.

Use `pwc-deploy` for a complete backend-plus-frontend release. Nginx changes use
the separate `pwc-nginx` command. The retired service scripts never mutate live
state. Scheduled work must use the installed `pwc-cron` allowlist; never run a
production job from `.github/workflows/scripts/` or source `backend/keys.env`
into a deployed process.

After any release, smoke-test `/health`, `/`, one SPA route, and one API route.
Restore the previous release if validation fails.

## Project map

Papers With Code is a React/Vite frontend with a FastAPI, SQLAlchemy, PostgreSQL,
and pgvector backend. Data comes from Hugging Face papers and the legacy dumps in
`data/legacy_pwc_data/`; scheduled imports and refreshes live under
`.github/workflows/scripts/`.

- Production: `https://paperswithcode.co`
- Local API: `http://localhost:8000/api/v1/`
- OpenAPI docs: `http://localhost:8000/docs`
- Development guide: `docs/development-guide.md`
- Database access: `docs/database.md`
- Data workflows: `docs/data-workflows.md`
- Operations: `docs/operations.md`
- CRON implementation: `.github/workflows/scripts/README.md`
- Schema: `docs/DATABASE_SCHEMA_UML.md`

# AGENTS.md

Guidance for agents working in this repository.

## Guardrails

- Production and staging run from immutable releases under
  `/srv/paperswithcode`; treat this checkout as production-adjacent release
  source, never as a runtime directory.
- During routine development, do not restart or stop services, kill processes,
  rebuild/repoint the production frontend, or reload nginx. Deploy only when the
  publishing workflow below calls for a release.
- Treat approval to implement a repository source change as approval to validate
  it, commit the intended changes directly to `main`, push `origin main`, and
  deploy that exact commit to production. Do not wait for separate commit, push,
  or production deployment requests unless the user explicitly asks for
  local-only work or no deployment. The chat-interface exception below always
  takes precedence.
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
  For large JSON arrays such as the legacy PwC dumps, prefer incremental parsing
  with `ijson`; never load the entire file with `json.load()`.

## Development

- Put domain logic in `backend/services/`, HTTP adapters in `backend/routers/`,
  API models in bounded modules under `backend/models/` (with
  `backend/models/api.py` as the compatibility re-export surface), and persistence models/migrations in
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
  pushed commit to production with `pwc-deploy`.
- Changes related to the chat interface at `staging.paperswithcode.co/chat`,
  including chat-specific frontend, backend, configuration, and infrastructure,
  must be deployed only to staging unless the user explicitly authorizes that
  chat work for production. Do not include chat-related changes in a production
  release merely because the same task also contains non-chat changes.
- Keep chat-related and non-chat source changes in separate commits when needed
  for deployment. Deploy the non-chat commit to production and the chat commit
  to staging; if they cannot be safely separated, stop before deployment and ask
  the user how to proceed.
- Planning documents (`PLAN*.md`), scratch notes, temporary artifacts,
  diagnostic output, and generated reports are local working files by default.
  Do not stage, commit, push, or deploy them unless the user explicitly asks to
  publish that specific file.
- A task that changes only local working files does not require a commit, push,
  or deployment. When a task also changes publishable source, commit only the
  intended source changes and leave local working files unstaged.
- Read-only investigation and reporting, data-only curation, database operations,
  and other work that does not change deployed source do not require a commit or
  application deployment.
- Do not create a feature branch or pull request unless the user explicitly
  requests one.
- Fetch `origin main` before publishing and never force-push. If local and
  remote `main` have diverged, stop and resolve the divergence safely before
  pushing.
- Production deployment is the default for publishable non-chat source changes.
  Staging deployment or implementation approval for chat-related work never
  implies authorization to deploy that chat work to production.

## Production releases

Production topology can change, so inspect the active processes and nginx config
before a release. Currently:

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

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for `huggingface/paperswithcode`. See
`docs/agents/issue-tracker.md`.

### Domain docs

This is a single-context repository. See `docs/agents/domain.md`.

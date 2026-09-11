# AGENTS.md

Guidance for agents working in the Papers with Code monorepo. The site at
https://paperswithcode.co makes open AI research and its artifacts accessible.
It runs on a Hetzner CPX42 with 8 vCPUs, 16 GB RAM, and an 80 GB disk.

## Guardrails

- Production and staging use immutable releases under `/srv/paperswithcode`;
  this checkout is production-adjacent release source, not a runtime directory.
- During development, do not stop services, kill processes, rebuild or repoint
  the production frontend, reload nginx, or otherwise mutate live runtime state.
- Preserve public API, route, CLI, and persisted-data contracts. Compatibility is
  optional only for clearly unshipped internal work.
- Keep logic simple and readable; avoid broad defensive `try`/`except` blocks.
- Preserve unrelated work in dirty trees and edit files narrowly.
- Run Python and repository CLIs with
  `uv run --env-file backend/keys.env …`. Read `docs/database.md` before
  accessing PostgreSQL.
- Prefer `DBPaper.is_latest_version` to `== True` and
  `~DBPaper.urls_extracted` to `== False`.
- Disk headroom is limited. Stream large inputs, use bounded batches, and check
  capacity first. Parse large JSON arrays incrementally with `ijson`; never load
  an entire legacy dump with `json.load()`.

## Development workflow

- Give each feature request and non-hotfix bug fix an isolated worktree and a
  dedicated `codex/<short-feature-name>` branch. If Codex supplies a
  detached-HEAD worktree, create the branch before the first commit. Do not
  develop independent features in the primary `main` checkout.
- Commit only the task's intended changes. Never switch, reset, delete, or reuse
  another task's worktree or branch.
- Implementation approval includes validation, a commit to the task branch,
  pushing that branch, and opening a GitHub pull request. Feature requests and
  non-hotfix bug fixes then stop and report their PR and verification; they do
  not update `main` or deploy before the PR is merged.
- Concurrent feature tasks are allowed, but one explicitly designated publishing
  task must serialize integration, pushing, and deployment.
- Put domain logic in `backend/services/`, HTTP adapters in `backend/routers/`,
  API models in bounded modules under `backend/models/` (with
  `backend/models/api.py` as the compatibility re-export surface), and
  persistence models and migrations in `backend/models/database.py` and
  `backend/database/migrations/`.
- Run targeted tests and linters; a focused check is preferable to the entire
  suite when sufficient.
- For an isolated backend, first confirm a free non-production port. Ports 8000
  and 8001 belong to production and staging.
- For frontend work, use `npm run dev` and `npm run lint`. Do not routinely run
  `npm run build`; it writes `frontend/dist` and consumes scarce disk. Define
  routes before the catch-all, and use `frontend/src/lib/api.ts` with TanStack
  Query for server state.

## Publishing and releases

- Urgent hotfixes that restore broken production or staging behavior may always
  be validated, committed, and pushed directly to `main`, then deployed as that
  exact commit with `pwc-deploy` under the environment rules below.
- Feature requests and all bug fixes that are not urgent service-restoration
  hotfixes must reach `main` through a merged GitHub pull request. The publishing
  task fetches the merged `origin main`, reruns proportionate validation, and
  deploys that exact commit with `pwc-deploy`.
- Before merging any pull request, wait for Cursor Bugbot to finish its review
  and resolve every Bugbot comment. Do not merge while its review is still in
  progress or any Bugbot comment remains unresolved.
- Never force-push. If local and remote `main` have diverged, stop and resolve the
  divergence safely before pushing.
- Production is the default for publishable non-chat source changes unless the
  user requests local-only work or no deployment.
- Chat-interface changes for `staging.paperswithcode.co/chat`—including its
  frontend, backend, configuration, and infrastructure—go only to staging unless
  the user explicitly authorizes production. Keep chat and non-chat changes in
  separate commits when necessary. If they cannot be separated safely, ask the
  user before deployment.
- Planning documents (`PLAN*.md`), scratch notes, temporary artifacts,
  diagnostic output, and generated reports are local by default. Do not stage,
  commit, or publish them unless explicitly requested. Tasks changing only local
  files need no commit or deployment; read-only investigations, data curation,
  and database operations need no application deployment.
- Inspect active processes and nginx configuration before releasing. Currently,
  production is `paperswithcode-backend@production` on `:8000`, staging is
  `paperswithcode-backend@staging` on `:8001`, and nginx serves each environment's
  `current/frontend-dist`.
- Use `pwc-status`, `pwc-deploy`, and `pwc-rollback` for lifecycle operations.
  Use `pwc-nginx` separately for nginx changes. Retired service scripts never
  mutate live state.
- Scheduled production work must use the installed `pwc-cron` allowlist. Never
  run a production job from `.github/workflows/scripts/` or source
  `backend/keys.env` into a deployed process.
- After a release, smoke-test `/health`, `/`, one SPA route, and one API route.
  Restore the previous release if validation fails.

## Project map

Papers With Code uses React/Vite, FastAPI, SQLAlchemy, PostgreSQL, and pgvector.
Data comes from Hugging Face papers and legacy dumps in `data/legacy_pwc_data/`;
scheduled imports and refreshes live under `.github/workflows/scripts/`.

- Production: `https://paperswithcode.co`
- Staging: `https://staging.paperswithcode.co`
- Local API: `http://localhost:8000/api/v1/`
- OpenAPI: `http://localhost:8000/docs`
- Development: `docs/development-guide.md`
- Database: `docs/database.md`
- Data workflows: `docs/data-workflows.md`
- Operations: `docs/operations.md`
- CRON: `.github/workflows/scripts/README.md`
- Schema: `docs/DATABASE_SCHEMA_UML.md`

## Agent docs

- GitHub issue workflow: `docs/agents/issue-tracker.md`
- Domain context: `docs/agents/domain.md`

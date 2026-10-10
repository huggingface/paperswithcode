# AGENTS.md

Guidance for agents working in the Papers with Code monorepo. The site at
https://paperswithcode.co makes open AI research and its artifacts accessible.
It runs on a Hetzner CPX42 with 8 vCPUs, 16 GB RAM, and an 80 GB disk.

## Guardrails

- Production and staging use immutable releases under `/srv/paperswithcode`;
  this checkout is production-adjacent release source, not a runtime directory.
- During development, do not stop services, kill processes, rebuild or repoint
  the production frontend, reload nginx, or otherwise mutate live runtime state.
- Run development nginx instances and config checks as an unprivileged user,
  with explicitly isolated temporary directories, logs, PID, and lock files.
  Never run a root-owned test instance using nginx's default paths: it can
  change production directory ownership even with a separate port, config, or
  `-p` prefix. Follow [the safe nginx test example](docs/development-guide.md#isolated-nginx-tests).
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
  dedicated `<agent>/<short-feature-name>` branch, where `<agent>` is the name
  of the coding agent doing the work (for example `codex/…`, `claude/…`,
  `cursor/…`). If the agent supplies a detached-HEAD worktree, create the
  branch before the first commit. Do not develop independent features in the
  primary `main` checkout.
- Commit only the task's intended changes. Never switch, reset, delete, or reuse
  another task's worktree or branch.
- Implementation approval includes validation, committing and pushing the task
  branch, opening a GitHub pull request, completing review, merging, and deploying
  under the environment rules below for non-chat changes. Continue through this
  workflow without waiting for another user request, unless the user requested
  local-only work, a draft PR, no merge, or no deployment. Chat-related changes
  stop after opening the PR and reporting verification; do not merge or deploy
  them unless the user explicitly authorizes it. Do not update `main` or deploy
  before the PR is merged. Documentation-only changes need no application
  deployment.
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
- For pull requests in `huggingface/paperswithcode`, wait for Cursor Bugbot to
  finish reviewing the latest head commit. Read its review and all review
  threads and other reviewer comments, address every finding, validate and push
  fixes, and wait for Bugbot again after each push. Resolve addressed threads
  before merging. Do not treat
  an absent, queued, or in-progress review as approval. Bugbot runs only in this
  repository; do not wait for it in other repositories.
- For non-chat changes, once review is complete, all review findings are
  addressed, and required checks pass, merge without asking again. Fetch the
  merged `origin/main`, rerun proportionate validation, deploy that exact commit to the authorized
  environment, and review the live result with the smoke checks below. Report
  the PR, release, and verification. If a check or review service fails or stays
  unavailable, investigate and report the blocker instead of bypassing the gate.
- Never force-push. If local and remote `main` have diverged, stop and resolve the
  divergence safely before pushing.
- Production is the default for publishable non-chat source changes unless the
  user requests local-only work or no deployment.
- Chat-related changes—including frontend, backend, configuration, and
  infrastructure—require explicit user authorization to merge and deploy,
  including urgent chat hotfixes. When deployment is authorized, use staging
  unless the user explicitly authorizes production. Keep chat and non-chat
  changes in separate PRs. If they cannot be separated safely, apply the chat
  authorization requirement to the entire PR.
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

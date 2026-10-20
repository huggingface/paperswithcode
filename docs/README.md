# PapersWithCode documentation

Keep documentation short and tied to a workflow. The code, FastAPI `/docs`, and
the database schema are the source of truth for implementation details.

## Living guides

- `development-guide.md` — conventions and local checks.
- `database.md` — database access and security.
- `DATABASE_SCHEMA_UML.md` — current schema reference.
- `data-workflows.md` — datasets, evaluations, metrics, and task hierarchy.
- `keyword-matching.md` — keyword behavior and bulk relinking.
- `deployment.md` — slots, releases, networking, and chat runtime release checks.
- `operations.md` — CRON timers, monitoring, curation, and admin review.
- `autonomous-operations.md` — autonomous curation operator and alerting.
- `public-api.md` — public API limits, docs, and changelog.
- `paper-agent-edits.md` — contributor and agent direct catalog edits.
- `paper-embeddings.md` — paper embedding generations and refresh.
- `research-follows.md` — research follows and email digests.
- `seo-operations.md` — robots, sitemaps, Search Console, and SEO checks.
- `chat-pwc-mcp.md` — chat's Papers With Code MCP tools.
- `chat-trackio.md` — chat trace and feedback export to Trackio.
- `chat-sandbox-spend-runbook.md` — chat sandbox spend caps and recovery.
- `latex-compiler-runbook.md` — staging LaTeX compiler sandbox.
- `agents/` — agent issue-tracker and domain-context conventions.
- `task-completion/` — durable field maps, top-100 ledgers, and verification reports
  produced by whole-task curation runs.

The root `README.md` covers setup. `AGENTS.md` contains the short contributor
quickstart. Cron-specific implementation details live beside the cron scripts in
`.github/workflows/scripts/README.md`.

## Writing Guidelines

- Prefer code and tests over explanatory prose.
- Keep only instructions that are not obvious from the code or command help.
- Keep examples executable (`uv run --env-file backend/keys.env …`, `npm run …`).
- Link to the owning code path instead of duplicating its implementation.

## Quick Links

- API docs (local): `http://localhost:8000/docs`
- Frontend dev server: `http://localhost:5173`
- Production: `https://paperswithcode.co`

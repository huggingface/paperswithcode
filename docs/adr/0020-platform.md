# ADR 0020: Database, runtime, deployment and testing

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## Application connections disable PostgreSQL JIT

PostgreSQL JIT-compiles any plan whose estimated cost passes jit_above_cost. Catalog queries finish in tens of milliseconds, but JIT compilation added roughly 0.5 s to each affected request. Application connections therefore set `jit=off` in their connection options.

Code: `backend/database/connection.py::DatabaseManager.engine`

## Connection pool size is an aggregate budget split across workers

Production keeps a small pool because it shares PostgreSQL with CRON jobs, while staging is sized for the isolated 32-turn chat durability qualification. The staging budget is divided by WEB_CONCURRENCY so adding Uvicorn workers cannot multiply the total number of connections.

Code: `backend/database/connection.py::database_pool_configuration`

## Curator jobs image is pinned by host-environment tooling

The application settings leave codex_jobs_image empty. Each deployment pins its own immutable curator image by digest, and production's pin lives in the host-environment tooling rather than the application defaults, so a code release cannot silently change the curator image.

Code: `backend/tests/curation/test_codex_add_evals.py::test_remote_job_uses_immutable_curator_image`

## DB checkout fails fast under burst traffic

The pool checkout timeout is kept short (5 s) so that under burst traffic requests fail quickly and release worker threads instead of queueing behind the pool until Cloudflare's upstream timeout expires.

Code: `backend/database/connection.py::DatabaseManager.engine`

## OpenRouter generator defaults to paid-tier rate limits

OpenRouter documents 20 requests/minute and 1000 requests/day limits, but those apply only to :free model variants. The project uses a paid account and a paid model, so OpenRouterGenerator defaults to 200 requests/minute and 10000 requests/day. Lowering the defaults to the documented free-tier limits would needlessly throttle batch generation.

Code: `backend/generators/openrouter_generator.py::OpenRouterGenerator.__init__`

## Pattern-origin CORS middleware wraps CORSMiddleware

Starlette applies middleware in reverse order of registration, so a middleware added later wraps earlier ones. PatternOriginsWithoutCredentials is added after CORSMiddleware so it sees and can adjust the CORS headers CORSMiddleware produced for origins matched by the extra pattern; reordering would break that.

Code: `backend/utils/cors.py::install_cors`

## Production backend runs multiple uvicorn workers; development uses one reloading worker

Uvicorn cannot combine auto-reload with multiple workers. Development runs a single auto-reloading worker, while production runs two workers so one slow request cannot stall every other in-flight request. Raising the count must respect the 16 GB VPS memory budget.

Code: `backend/run_server.py::main`

## SQLite test fixtures map BigInteger primary keys to Integer

SQLite only autoincrements primary keys declared exactly INTEGER. Test fixtures that rebuild the ORM tables on SQLite therefore map BigInteger primary keys to Integer; otherwise inserts without explicit ids fail with NOT NULL errors.

Code: `backend/tests/curation/test_release_signal_resolution.py::db`

## SQLite test schemas map BigInteger primary keys to Integer

Tests that mirror PostgreSQL models into in-memory SQLite convert BigInteger primary keys to Integer, because SQLite only autoincrements INTEGER PRIMARY KEY columns. Without the conversion inserts without explicit ids fail.

Code: `backend/tests/curation/test_external_paper_curation.py::db`

## SQLite tests emulate PostgreSQL DESC NULL ordering

SQLite sorts NULLs last for DESC while production PostgreSQL sorts them first. Endpoint tests for trending ordering rewrite statements to reproduce PostgreSQL's NULL ordering, so regressions where unscored papers jump to the top remain visible in the in-memory suite; production queries must specify NULLS LAST explicitly.

Code: `backend/tests/taxonomy/test_tasks_api.py::test_task_papers_trending_composite_puts_fresh_null_scores_last`

## Schema-constrained generations are coerced to the Pydantic model

Some generators (notably GoogleGenerator) return a dict or JSON string rather than a parsed Pydantic instance even when a schema is requested. Callers of generate with a schema coerce dict and str responses into the model before use.

Code: `backend/genai_steps/extract_external_resource_metadata.py::extract_external_resource_metadata`

## Search-vector backfills run in replica mode to preserve updated_at

Rewriting papers.search_vector is an index maintenance operation, not a content change, but the papers updated_at trigger would otherwise bump every row and disturb freshness-based logic. The backfill sets session_replication_role = replica per transaction so user triggers are skipped. This requires a PostgreSQL superuser connection.

Code: `backend/database/migrations/backfill_paper_search_vector.py::rebuild`

## Staging app connections opt out of the role's read-only default

The staging PostgreSQL role defaults to `default_transaction_read_only=on` so ad hoc logins cannot write by accident. The staging application explicitly sets `default_transaction_read_only=off` on its connections; database privileges still restrict those writes to the staging-owned schema. Removing the option makes every staging write fail.

Code: `backend/database/connection.py::DatabaseManager.engine`

## Star history relies on its unique constraint for per-repo reads

The uq_repo_snapshot_time unique constraint on (repository_id, snapshot_at) also serves newest-first reads per repository, and idx_star_history_recent (created in a migration, not the ORM model) serves snapshot_at scans. Redundant star-history indexes were dropped (drop_redundant_star_history_indexes.sql); do not re-add them in the model.

Code: `backend/models/database/resources.py::RepositoryStarHistory`

## Structured-extraction prompts go in a single user message

Several LLM providers reached through OpenRouter (e.g. Gemini) reject a system role. External resource metadata extraction therefore prepends its instructions to the single user message instead of sending a system message.

Code: `backend/genai_steps/extract_external_resource_metadata.py::extract_external_resource_metadata`

## Test DB guard patches psycopg2.connect

The test-suite database guard replaces `psycopg2.connect` rather than wrapping a specific engine. SQLAlchemy's psycopg2 dialect resolves `psycopg2.connect` at connect time, so the guard also covers engines created later from `db_manager`, preventing tests from reaching a production database.

Code: `backend/tests/conftest.py::pytest_configure`

## Autonomous CRON source repair writes only job-owned files

A CRON source repair may edit only the failing job's own entry script, the services listed for it in `_OWNED_SERVICE_PATHS`, and tests. The shared CRON dashboard and launcher files also carry chat-monitor behavior, so they are never writable by a non-chat CRON repair; changes to them go through a human pull request. There is deliberately no shared-source allowlist.

Source repair is further limited to `_SAFE_SOURCE_REPAIRS` (the trending-score jobs). Every other job runs as the application database role, which can create tasks, methods, and other taxonomy rows, so letting an agent rewrite and rerun it would breach the hard boundary that autonomous code never creates taxonomy. Widening the set requires a PostgreSQL role for repaired jobs that has no INSERT, UPDATE, or DELETE privilege on taxonomy tables (tracked in issue #1113).

Code: `backend/services/autonomous_cron_operator.py::build_cron_repair_contracts`

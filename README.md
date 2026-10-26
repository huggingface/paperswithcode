# Papers with Code

Papers with Code makes open AI research and its artifacts accessible: papers,
code, models, datasets, tasks, methods, and benchmark leaderboards. It recreates
the original paperswithcode.com, which Meta retired in 2025, and keeps it up to
date with automated imports from Hugging Face, arXiv, GitHub, and public
leaderboards.

**Live site:** https://paperswithcode.co

## Features

- **Paper catalog.** arXiv and external papers with official code, project
  pages, Hugging Face models, datasets, and Spaces, plus thumbnails, TL;DRs,
  lineage, and a Markdown reader.
- **Taxonomy.** Browsable tasks, methods, datasets, frameworks, conferences,
  organizations, and authors, with trending views.
- **Leaderboards.** Paper-native evaluation results on benchmarks, plus
  scheduled syncs of external leaderboards.
- **Search.** Hybrid lexical (`pg_trgm`) and semantic (`pgvector`) paper
  retrieval.
- **Public API.** A REST API under `/api/v1/` that stays compatible with the
  original [Papers with Code API client](https://github.com/paperswithcode/paperswithcode-client).
  OpenAPI docs are served at `/docs`.
- **Research chat (optional).** An assistant grounded in the catalog through the
  Papers with Code MCP tools.
- **Curation automation.** Scheduled jobs and agent workflows import daily
  papers, link tasks and methods, refresh stars and citations, and propose
  evaluations.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, TanStack Query, shadcn/ui, Tailwind CSS |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic |
| Database | PostgreSQL 16 with the `vector` and `pg_trgm` extensions |
| Tooling | [uv](https://docs.astral.sh/uv/), npm, Ruff, pytest |
| Hosting | nginx serving immutable releases ([deploy/](deploy/)) |

## Repository layout

| Path | Contents |
|---|---|
| [`backend/`](backend/) | FastAPI app (`main.py`), `routers/` (HTTP adapters), `services/` (domain logic), `models/` (API models; `models/database/` for SQLAlchemy models), `database/migrations/` (SQL migrations), `cli.py` (the `pwc` maintenance CLI), and `tests/` |
| [`frontend/`](frontend/) | React single-page app |
| [`deploy/`](deploy/) | Release, rollback, nginx, systemd, and environment templates for the hosted site |
| [`.github/workflows/`](.github/workflows/) | CI and scheduled data jobs; job scripts live in `scripts/` |
| [`jobs/`](jobs/) | Paper-curation runner for Hugging Face Jobs |
| [`docs/`](docs/) | Development, data, database, and operations guides |

## Local development

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/), which
  installs Python 3.12 for you
- Node.js 18+ and npm
- PostgreSQL 16 with [pgvector](https://github.com/pgvector/pgvector)

### 1. Install dependencies

```bash
git clone https://github.com/huggingface/paperswithcode.git
cd paperswithcode
uv sync
cd frontend && npm install && cd ..
```

### 2. Create a database

```bash
createdb paperswithcode
psql -d paperswithcode -c 'CREATE EXTENSION vector' -c 'CREATE EXTENSION pg_trgm'
```

### 3. Configure the environment

Settings are read from `PWC_`-prefixed environment variables (see
[`backend/config.py`](backend/config.py)). Put them in `backend/keys.env`,
which git ignores:

```env
PWC_DB_HOST=localhost
PWC_DB_PORT=5432
PWC_DB_NAME=paperswithcode
PWC_DB_USER=postgres
PWC_DB_PASSWORD=
PWC_ENVIRONMENT=development

# Optional: higher Hugging Face and GitHub rate limits for imports
PWC_HF_TOKEN=
PWC_GITHUB_TOKEN=
```

Chat, curation, and hosted integrations need more credentials; the
templates in [`deploy/env/`](deploy/env/) list them.

### 4. Create the schema and run the app

```bash
uv run --env-file backend/keys.env python -m backend.database.connection init
uv run --env-file backend/keys.env backend/run_server.py   # API on http://localhost:8000
cd frontend && npm run dev                                   # app on http://localhost:8080
```

The Vite dev server proxies `/api` to the backend on port 8000. The schema
starts empty; use the `pwc` CLI below to index papers.

### Tests and linting

```bash
uv run pytest backend/tests/paper -q    # run the suite you touched
cd frontend && npm run lint
```

Tests that need PostgreSQL refuse to run unless `PWC_TEST_DATABASE=1` points
them at a disposable database. The
[development guide](docs/development-guide.md) lists the test suites and
conventions. [pre-commit](https://pre-commit.com/) runs Ruff on each commit;
run `pre-commit install` once to enable it.

## The `pwc` maintenance CLI

`uv sync` installs a `pwc` command for catalog maintenance. Run
`uv run pwc --help` for the full list. Common commands:

```bash
uv run --env-file backend/keys.env pwc paper index 1706.03762    # index or refresh an arXiv paper
uv run --env-file backend/keys.env pwc paper info 1706.03762
uv run --env-file backend/keys.env pwc search "vision-language models"
uv run --env-file backend/keys.env pwc paper add-external https://example.org/research
uv run --env-file backend/keys.env pwc benchmark add "ExampleBench" \
  --task question-answering --metric Accuracy --source-paper 2501.12345
uv run --env-file backend/keys.env pwc thumbnail 1706.03762      # regenerate a thumbnail
uv run --env-file backend/keys.env pwc cron health               # scheduled-job health
```

For read-only access to the public catalog from any machine, install the
standalone [`pwc-cli`](https://github.com/huggingface/pwc-cli):

```bash
uv tool install 'git+https://github.com/huggingface/pwc-cli.git#subdirectory=standalone_cli'
```

## Hosted deployment

paperswithcode.co runs production and staging as immutable releases behind
nginx; see [docs/deployment.md](docs/deployment.md) and
[docs/operations.md](docs/operations.md). Durable artifacts live in private
Hugging Face buckets in the `huggingface` organization:

| Bucket | Purpose | Setting |
|---|---|---|
| `huggingface/pwc-papers-content` | Paper Markdown used by the reader and `pwc paper read` | `PWC_PAPER_MARKDOWN_HF_BUCKET_ID` |
| `huggingface/pwc-thumbnail` | Generated paper thumbnails | `PWC_THUMBNAIL_HF_BUCKET_ID` |
| `huggingface/pwc-paper-embeddings` | Embedding exports and experiments | `hf://buckets/huggingface/pwc-paper-embeddings/...` |
| `huggingface/paperswithcode-backups` | Database backups | `PWC_POSTGRES_BACKUP_BUCKET` |

## Documentation

- [docs/development-guide.md](docs/development-guide.md): conventions, test suites, and local checks
- [docs/public-api.md](docs/public-api.md): the public REST API
- [docs/database.md](docs/database.md): database access and security
- [docs/DATABASE_SCHEMA_UML.md](docs/DATABASE_SCHEMA_UML.md): schema reference
- [docs/data-workflows.md](docs/data-workflows.md): datasets, evaluations, metrics, and tasks
- [docs/operations.md](docs/operations.md): scheduled jobs and monitoring
- [docs/deployment.md](docs/deployment.md): releases, nginx, and smoke checks
- [.github/workflows/scripts/README.md](.github/workflows/scripts/README.md): scheduled job scripts
- [AGENTS.md](AGENTS.md): instructions for coding agents

## Security

Please report vulnerabilities privately; see [SECURITY.md](SECURITY.md).

## License

Papers with Code is licensed under the [Apache License 2.0](LICENSE).

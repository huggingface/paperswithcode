# PapersWithCode

A complete recreation of paperswithcode.com built with modern web technologies.

🌐 **Live Site**: https://paperswithcode.co (HTTPS enabled)

## Project info

This project aims to re-implement PapersWithCode and make it available for everyone.

Based on this initial Lovable design: https://lovable.dev/projects/a4609afe-13e0-46bd-8d20-9226da85ef46

## 🚀 Quick Start

### Production (HTTPS)

The site is deployed at **https://paperswithcode.co** with Nginx reverse proxy and Let's Encrypt SSL.

**Setting up HTTPS**: See [`docs/deployment.md`](docs/deployment.md)

### Development

Run the backend and frontend locally on developer-selected ports:

```bash
uv run --env-file backend/keys.env backend/run_server.py
cd frontend && npm run dev
```

Production and staging lifecycle commands are documented in
[`docs/deployment.md`](docs/deployment.md); the legacy start/stop scripts are
non-mutating retirement notices.

## Project structure

The project consists of a `backend` folder (which implements a FastAPI app which connects to a [PostGresSQL](https://www.postgresql.org/) database) and a `frontend` folder. The backend re-implements the [PapersWithCode API](https://github.com/paperswithcode/paperswithcode-client) formerly maintained by Meta.

## Set-up

We use [uv](https://docs.astral.sh/uv/) to handle Python package management. It can be installed like so:

```bash
pip install uv
```

Install the standalone, read-only `pwc` CLI directly from the repository with
either uv or pipx:

```bash
uv tool install 'git+https://github.com/huggingface/paperswithcode.git#subdirectory=standalone_cli'
# or
pipx install 'git+https://github.com/huggingface/paperswithcode.git#subdirectory=standalone_cli'
```

For repository development, clone the full project and let uv install its
dependencies:

```bash
git clone https://github.com/huggingface/paperswithcode.git
cd paperswithcode
uv sync
```

After that, use `uv run --env-file backend/keys.env` to run repository commands.

### PwC CLI

Repository maintenance workflows are exposed through the `pwc` command. For
example, generate a rule-based GitHub issue body from a paper's current
paper-native evaluations:

```bash
uv run --env-file backend/keys.env pwc github-issue body 2601.21998
```

Use `--verified` only after a human verification pass, and `--json` when the
caller also needs the issue title, official repository candidates, computed
rankings, and other structured metadata:

```bash
uv run --env-file backend/keys.env pwc github-issue body 2601.21998 --verified --json
```

Creating the issue is a separate, duplicate-safe command. It resolves only
official repositories and requires an explicit publication confirmation:

```bash
uv run --env-file backend/keys.env pwc github-issue create 2601.21998 \
  --verified --confirm PUBLISH
```

Regenerate and validate a paper thumbnail using an arXiv ID, Papers with Code
URL, or numeric external-paper ID:

```bash
uv run --env-file backend/keys.env pwc thumbnail 2512.20856
```

The command forces regeneration by default, reports old and new dimensions,
and exits non-zero when the JPEG is not a 400px-wide portrait render. PDF
thumbnails preserve the source page aspect ratio, so their height is variable
(for example, a Letter page is about 400×518). Use `--no-force` to reuse a
valid cached thumbnail or `--json` for structured output.

Download, self-host, and attribute a hero image for an existing task, method,
or conference. The command keeps a seed copy in `data/entity_image_seeds/` and
stores the image bytes and source credit on the database row:

```bash
uv run --env-file backend/keys.env pwc image add task object-detection \
  https://example.org/object-detection.png \
  --source https://example.org/object-detection
```

Manage directed paper lineage using unambiguous paper references. Supplying
more than two papers creates each adjacent predecessor-to-successor edge:

```bash
uv run --env-file backend/keys.env pwc paper lineage add \
  1810.04805 2005.14165 2303.08774
uv run --env-file backend/keys.env pwc paper lineage list 2005.14165
uv run --env-file backend/keys.env pwc paper lineage remove \
  1810.04805 2005.14165 --confirm DELETE
```

Index or refresh an ArXiv paper, and replace one category of its curated
metadata using a PwC URL, ArXiv ID, or numeric external-paper ID:

```bash
uv run --env-file backend/keys.env pwc paper index 2501.12345
uv run --env-file backend/keys.env pwc paper read 1706.03762
uv run --env-file backend/keys.env pwc paper update 2501.12345 tasks 12 34
uv run --env-file backend/keys.env pwc paper update 2501.12345 repositories \
  https://github.com/example/official \
  --unofficial https://github.com/example/community
```

`pwc paper read` prints the paper Markdown stored in the private Hugging Face
bucket configured by `PWC_PAPER_MARKDOWN_HF_BUCKET_ID` (default:
`huggingface/pwc-papers-content`). It accepts a modern ArXiv ID or a full
`paperswithcode.co/paper/...` URL.

Inspect and browse the paper catalog directly through the same services as the
API. Search uses hybrid lexical and semantic retrieval by default:

```bash
uv run --env-file backend/keys.env pwc search "vision-language models"
uv run --env-file backend/keys.env pwc paper info 2412.08443
uv run --env-file backend/keys.env pwc paper list --conference ICLR --page-size 20
uv run --env-file backend/keys.env pwc paper recent --limit 10
uv run --env-file backend/keys.env pwc paper trending --limit 10
uv run --env-file backend/keys.env pwc paper related 2412.08443
```

External research pages can be extracted and ingested with optional metadata
overrides. Benchmarks support the same task and text filters as the list API:

```bash
uv run --env-file backend/keys.env pwc paper add-external https://example.org/research
uv run --env-file backend/keys.env pwc benchmark list --task object-detection
```

Create or reuse a benchmark, link it to existing tasks and metrics, and attach
its introducing paper using a native Papers with Code paper URL:

```bash
uv run --env-file backend/keys.env pwc benchmark add "ExampleBench" \
  --description "A reproducible benchmark." \
  --task question-answering \
  --metric Accuracy \
  --source-paper 2501.12345
```

Inspect scheduled jobs by triangulating parsed logs, active processes, lock
files, database freshness, and available GitHub Actions state. The command
returns non-zero for broken or stuck jobs; add `--strict` to include degraded
and unknown jobs:

```bash
uv run --env-file backend/keys.env pwc cron health
uv run --env-file backend/keys.env pwc cron health update_github_stars --json
uv run --env-file backend/keys.env pwc cron health --strict
```

After rotating a CRON credential, probe it with the exact authentication style
used by the corresponding job without printing the secret:

```bash
uv run --env-file backend/keys.env pwc cron token-check PWC_GITHUB_TOKEN
```

Supported probes cover `PWC_GITHUB_TOKEN`, `PWC_HF_TOKEN`,
`PWC_OPENROUTER_API_KEY`, `PWC_SEMANTIC_SCHOLAR_API_KEY`, and the legacy
`PWC_GEMINI_API_KEY`.

### Hugging Face storage buckets

Durable project artifacts are stored in private Hugging Face buckets owned by
the `huggingface` organization. Keep project buckets in this organization
rather than creating them in a personal namespace.

| Bucket | Purpose | Configuration |
|---|---|---|
| [`huggingface/pwc-papers-content`](https://huggingface.co/buckets/huggingface/pwc-papers-content) | Markdown paper corpus used by `pwc paper read` | `PWC_PAPER_MARKDOWN_HF_BUCKET_ID` |
| [`huggingface/pwc-thumbnail`](https://huggingface.co/buckets/huggingface/pwc-thumbnail) | Generated paper thumbnails | `PWC_THUMBNAIL_HF_BUCKET_ID` |
| [`huggingface/pwc-paper-embeddings`](https://huggingface.co/buckets/huggingface/pwc-paper-embeddings) | Embedding exports, experiments, and summary-generation artifacts | Referenced through `hf://buckets/huggingface/pwc-paper-embeddings/...` URIs |
| [`huggingface/paperswithcode-backups`](https://huggingface.co/buckets/huggingface/paperswithcode-backups) | Encrypted/controlled production database backups | `PWC_POSTGRES_BACKUP_BUCKET` |

Access requires `PWC_HF_TOKEN` with permission to read the relevant private
organization bucket. Commands and jobs should use the fully qualified
`huggingface/<bucket>` ID so artifacts do not accidentally land under the
operator's personal account.

[Pre-commit](https://pre-commit.com/) is used to automatically run Ruff on the code base each time you contribute to the repository. See the `.pre-commit-config.yaml` file. On Ubuntu, it can be installed with `apt install pre-commit`. The hooks can then be installed using `pre-commit install`.

## How to run

The backend (written in Python) can be run as follows:

```bash
uv run backend/run_server.py
```

The frontend (written in Javascript) can be run as follows:

```bash
cd frontend
npm run dev
```

The backend (written in Python) can be run as follows:

```bash
cd backend
uv run
```

## 📚 Documentation

### Documentation
- **[docs/deployment.md](docs/deployment.md)** – DNS, HTTPS, and runtime verification
- **[docs/data-workflows.md](docs/data-workflows.md)** – Dataset/evaluation ingestion
- **[docs/database.md](docs/database.md)** – PostgreSQL access and security
- **[docs/operations.md](docs/operations.md)** – Cron jobs, trending pipeline, monitoring
- **[docs/keyword-matching.md](docs/keyword-matching.md)** – Keyword tagging strategy and APIs
- **[docs/DATABASE_SCHEMA_UML.md](docs/DATABASE_SCHEMA_UML.md)** – Schema reference
- **[AGENTS.md](AGENTS.md)** – Concise agent quickstart and links to `docs/`
- **[backend/README.md](backend/README.md)** – Backend setup
- **[.github/workflows/scripts/README.md](.github/workflows/scripts/README.md)** – Cron job guide

### Key Scripts
- **[setup_ssl.sh](setup_ssl.sh)** - Automated SSL certificate setup
- **[check_services.sh](check_services.sh)** - Delegate to read-only `pwc-status`
- **[deploy/](deploy/)** - Immutable release, rollback, nginx, and smoke tooling

## 🛠️ Tech Stack

- **Frontend**: React 18 + TypeScript + Vite + shadcn/ui + Tailwind CSS
- **Backend**: FastAPI + SQLAlchemy + PostgreSQL
- **Web Server**: Nginx + Let's Encrypt SSL
- **AI**: OpenRouter/Google Gemini for URL extraction
- **Package Management**: uv (Python), npm (JavaScript)

## TODOs

- all services should be checked to see if they are in line with the database schema (see also models.py)
- all cron jobs and batch_extract.py should leverage the services instead of manually writing SQL queries

## Improving extraction of evaluation results

- use pass@1 instead of accuracy on coding benchmarks
- when searching a dataset, thoroughly check which metric used to evaluate the dataset, and then use a separate agent to add the metric to the database/see if it already exists in the database.
- often adds "average", "overall" as metrics => should just be a single "Score" metric (higher is better or lower is better), or "OmniContext Score" for example with a specific scale like 0-10.
- messes up the dataset, e.g. for the Qwen2.5 paper, it links "LongBench-Chat" to the "LongBenchv2" dataset, which is a separate dataset. Step 2 requires an improvement by better matching the dataset details of the paper (e.g. description, arxiv id) to the existing dataset in the database.

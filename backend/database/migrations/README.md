# Database Migrations

Schema migration scripts for the PapersWithCode backend. One-off data curation
migrations (method rows, benchmark backfills, task reorganizations) are removed
after they land in production — use the agent skills under `.agents/skills/`
for new curation work instead.

## Running migrations

SQL-only (idempotent `IF NOT EXISTS` / `IF EXISTS`):

```bash
psql -U postgres -d paperswithcode_hf -f backend/database/migrations/<file>.sql
```

With a Python wrapper (applies SQL + verification / rank recalculation):

```bash
uv run --env-file backend/keys.env python backend/database/migrations/run_<name>.py
```

## Current files

| Migration | Purpose |
| --- | --- |
| `add_v2_schema.sql` + `run_add_v2_schema.py` | `papers.tldr`, `papers.num_pages` |
| `add_entity_image_data.sql` + `run_add_entity_image_data.py` | DB-backed `image_data`/`image_mime_type` on `tasks`/`methods`/`conferences` (bulk backfill from `data/entity_image_seeds/`; single-file import via `backend/database/import_entity_image.py`) |
| `add_paper_relations.sql` + `run_add_paper_relations.py` | `paper_relations` table |
| `add_pending_paper_edits.sql` + `run_add_pending_paper_edits.py` | pending edit queue |
| `allow_taxonomy_suggestions_without_paper.sql` | nullable paper association for task/method suggestions submitted from taxonomy directories |
| `add_user_bookmarks.sql` + `run_add_user_bookmarks.py` | user bookmarks |
| `add_chat_sessions.sql` | Authenticated chat sessions, UI messages, and opaque Agent SDK transcript storage |
| `add_chat_sandbox_runtime.sql` | Staging-only additive immutable chat backend selection, runtime provenance, sandbox leases, and hash-only turn capabilities; run as PostgreSQL superuser with `search_path=staging,public` before activating the bridge |
| `add_external_resources_schema.sql` + `run_add_external_resources_schema.py` | external resources |
| `add_trending_score.sql` + `run_add_trending_score.py` + `update_trending_view_for_ema.sql` | repository (GitHub) trending scores |
| `add_paper_hf_trending.sql` + `run_add_paper_hf_trending.py` | composite paper trending: `hf_artifacts`, `paper_hf_artifacts`, and `papers.trending_score`/components (rollback: `rollback_paper_hf_trending.sql`) |
| `add_dataset_variants_and_splits.sql` + `run_add_dataset_variants_and_splits.py` | dataset variants (rollback: `rollback_dataset_variants_and_splits.sql`) |
| `add_keywords_to_methods.sql` | methods keywords column (rollback: `rollback_keywords_from_methods.sql`) |
| `add_evaluations_num_parameters.sql` | `evaluations.num_parameters` |
| `add_evaluations_harness.sql` | `evaluations.harness` |
| `add_evaluations_hf_model_url.sql` | `evaluations.hf_model_url` |
| `add_evaluations_source_attribution.sql` | `evaluations.source_url` and `evaluations.external` |
| `add_task_datasets_supports_harness.sql` | `task_datasets.supports_harness` |
| `add_task_datasets_featured_rank.sql` | `task_datasets.featured_rank` |
| `add_tasks_is_visible.sql` | `tasks.is_visible` |
| `add_task_sister_tasks.sql` + `run_add_task_sister_tasks.py` | `task_sister_tasks` table (explicit sister tasks) |
| `add_task_recommended_frameworks.sql` | Ordered task-to-repository framework recommendations, with initial image-classification and object-detection data |
| `add_paper_tasks_source.sql` | `paper_tasks.source` |
| `add_methods_scanned_at_to_papers.sql` | `papers.methods_scanned_at` |
| `add_method_source_paper_id.sql` | `methods.source_paper_id` |
| `add_paper_performance_indexes.sql` | paper query indexes |
| `add_missing_dataset_variant_fields.sql` | dataset variant columns |

## Adding new migrations

- **Schema changes**: add idempotent SQL here; add a `run_*.py` wrapper when
  post-apply verification or service calls are needed (see `run_add_trending_score.py`).
- **Method / benchmark / task / eval curation**: do not add one-off SQL files — use
  `.agents/skills/add-method/`, `add-task/`, `add-benchmark/`, or `add-evals/` instead.

No Alembic. Migrations are applied manually on the VPS with `psql` or `uv run`.

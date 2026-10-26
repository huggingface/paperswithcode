# Keyword Matching & Management

## Shared Matching Module

- Location: `backend/utils/keyword_matching.py`
- Two strategies:
  - `find_matching_items_simple` – used for tasks; returns *all* matches.
  - `find_matching_items_longest_match` – used for methods; prevents overlapping/shorter matches (e.g., `GPT` vs `GPT-4`).
- Case handling (`is_case_sensitive_keyword`):
  - Keywords containing an uppercase letter match case-sensitively; all-lowercase keywords match case-insensitively.
  - All-lowercase keywords use a word-boundary regex with an optional plural `s` (`\b<keyword>s?\b`), so `transformer` matches `transformers` but not `transformed`.
  - Uppercase keywords also use that word-boundary rule for tasks, so `NER` does not match `FINER`; add compound acronyms such as `LVLMs` as their own task keywords. For methods, uppercase keywords are substring matches (captures `VLMs`, `OpenCLIP`).

## Where It’s Used

| File | Strategy | Purpose |
| --- | --- | --- |
| `.github/workflows/scripts/utils/hf_paper_importer.py` (used by `daily/import_hf_daily_papers.py`) | simple + longest | Auto-tag newly imported Hugging Face papers with tasks/methods. |
| `.github/workflows/scripts/weekly/link_papers_by_task_keywords.py` | simple | Weekly wrapper around the task backfill below for papers imported before a keyword changed. |
| `backend/database/tasks_setup/link_papers_by_task_keywords.py` | simple | Same matcher as the weekly cron; run manually for immediate backfills. |
| `backend/database/methods_setup/link_papers_by_keywords.py` | longest | Retag corpus for methods while honoring hierarchical names. |
| `backend/services/method_backfill_service.py` | longest | Bounded, resumable historical method-link backfills. |

The consolidation replaced dozens of one-off scripts; use git history for historical imports.

### Running Bulk Linking

```bash
uv run --env-file backend/keys.env backend/database/tasks_setup/link_papers_by_task_keywords.py
uv run --env-file backend/keys.env backend/database/methods_setup/link_papers_by_keywords.py
```

Task backfills can be scoped with repeated `--task-slug` when only a small
taxonomy subset changed. `--rebuild` deletes and recreates only automatic
(`source='auto'`) links for the selected tasks; manual links remain untouched:

```bash
uv run --env-file backend/keys.env \
  backend/database/tasks_setup/link_papers_by_task_keywords.py \
  --rebuild --task-slug image-generation --task-slug video-generation
```

Expect ~0.86 task tags and ~2.4 method tags per paper after the improved strategy (statistics from October 2025).

## Keywords API

Both tasks and methods expose keyword management endpoints:

```
POST   /api/v1/tasks/{task_id}/keywords
DELETE /api/v1/tasks/{task_id}/keywords
PUT    /api/v1/tasks/{task_id}/keywords

POST   /api/v1/methods/{method_id}/keywords
DELETE /api/v1/methods/{method_id}/keywords
PUT    /api/v1/methods/{method_id}/keywords
```

All three require a catalog mutator (for example the `X-Admin-Token` header);
contributors need a fresh session for `DELETE` and `PUT`. Example:

```bash
curl -X POST http://localhost:8000/api/v1/methods/function-calling/keywords \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN" \
  -d '{"keywords": ["function-calling", "tool-use"]}'
```

Implementation details:
- Keywords stored as comma-separated strings on the `keywords` column of `tasks` and `methods` tables.
- API resolves targets by numeric ID, slug, or (for methods) case-insensitive name.
- Service layer trims whitespace, skips exact duplicates, and supports full replacement via PUT.

## Maintenance Tips

- When adding new keywords, keep the casing rule in mind: lowercase for phrases, uppercase for acronyms/initialisms.
- Re-run bulk linking after changing keyword sets to backfill historical data.
- Monitor new acronyms (e.g., `LVLM`, `MCP`) and add them to method keywords promptly to maintain coverage.

## Future Ideas

- Keyword synonym tables (e.g., map `LLM` → `large language model`).
- Confidence scores or flags for ambiguous matches.
- Admin UI for reviewing suggested tags before promotion.

_Last updated: 20 October 2026_

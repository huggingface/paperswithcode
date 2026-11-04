# Data Workflows: Datasets & Evaluations

Guidelines for adding structured benchmark data through the API and service layer.  Always prefer API-first operations—the service stack handles validation, task/dataset linking, and rank recalculation.

Catalog writes require a catalog mutator: the admin token (`PWC_ADMIN_API_TOKEN`)
in the `X-Admin-Token` header, or a contributor/admin browser session (see
`backend/utils/auth.py`).

## Creating Datasets

```bash
curl -X POST "http://localhost:8000/api/v1/datasets/" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN" \
  -d '{
        "name": "Video-MMLU",
        "full_name": "Video-MMLU: Massive Multi-Discipline Lecture Understanding",
        "description": "Comprehensive benchmark for evaluating LMMs",
        "url": "https://enxinsong.com/Video-MMLU-web/",
        "hf_url": "https://huggingface.co/datasets/Enxin/Video-MMLU",
        "paper_url": "https://arxiv.org/abs/2504.14693",
        "task_ids": [9]
      }'
```

**Required fields:** `name`, `description`, `task_ids`.  Optional metadata (`url`, `hf_url`, `paper_url`, modalities, languages, license, introduced_date, …) is stored if provided; see `DatasetCreateRequest` in `backend/models/evaluations.py`.

Service behavior (`DatasetService.create_dataset`):
- Validates task IDs
- Generates slug and normalizes URLs
- Attaches dataset to requested tasks via `task_datasets`
- Returns the full serialized dataset model

### Verification

```bash
curl "http://localhost:8000/api/v1/datasets/?name=Video-MMLU"
curl "http://localhost:8000/api/v1/datasets/?task=9"
```

For one-off imports, use the `add-benchmark` and `add-evals` skills under `.agents/skills/` (remember `uv run --env-file backend/keys.env …`).

## Adding Evaluation Results

```bash
curl -X POST "http://localhost:8000/api/v1/evaluations/" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN" \
  -d '{
        "paper_id": 123,
        "task_id": 12,
        "dataset_id": 138,
        "model_name": "DETR-R50",
        "metrics": {"box AP": "44.9", "AP50": "64.7"},
        "best_metric": "box AP",
        "methodology": "End-to-end object detection with transformers"
      }'
```

The evaluation service (`EvaluationService.create_evaluation`):
- Rejects a `(task, dataset)` pair that has no `task_dataset_metrics` rows, i.e.
  is not a defined leaderboard
- Requires every `metrics` key and `best_metric` to be allowed for that
  leaderboard via `LeaderboardMetricService.validate_metrics_for_leaderboard`
- Accepts `harness` only when the leaderboard's `supports_harness` flag is set
- Recalculates leaderboard ranks (`best_rank`) after inserts/updates/deletes

List a leaderboard's allowed metrics with
`GET /api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics`.

### Triple Reminder

Leaderboards are keyed on `(task_id, dataset_id, metric_id)`.  Examples:
- `(Object Detection, COCO, box AP)`
- `(Image Classification, Imagenet-1k (ILSVRC-2012), Top-1 Accuracy)`
- `(World Knowledge, MMLU, Accuracy)` — the `task_id` here is the
  `world-knowledge` *subtask* (a child of `language-modeling`), not the
  parent task. Always pick the most-specific task in the hierarchy.

If you are unsure which metrics are allowed for a task/dataset pair, use the metrics endpoint above, `LeaderboardMetricService.get_allowed_metrics_for_leaderboard`, or query `task_dataset_metrics`.

### Subtasks (Task Hierarchy)

Tasks form a tree via `tasks.parent_id`. Subtasks are first-class child rows
with their own slug, description, page, benchmarks, and evaluations.

When writing benchmark/evaluation data:

- Always pick the most-specific (deepest) task that fits the benchmark.
- Move existing parent-task benchmarks to the right subtask via an idempotent
  SQL migration under `backend/database/migrations/`, then recalculate ranks with
  `EvaluationService.recalculate_ranks`.
- Do not duplicate the same benchmark on both a parent task and one of its
  subtasks; leaderboards then have ambiguous ownership.

When reading data for a parent task page:

- `/api/v1/datasets/?task=<parent>&include_descendants=true` returns
  benchmarks owned by every descendant subtask.
- `/api/v1/evaluations/?task_id=<parent>&include_descendants=true` returns
  evaluations from every descendant subtask.
- The parent task's children are listed via `/api/v1/tasks/{task_id}/children`.

### Bulk Imports

- `backend/database/evaluations_setup/paper_eval_import.py` provides import helpers around `EvaluationService`, the same service used by the API.
- Always run the validation script afterwards (see below).

## Metric Naming & Direction

- Store canonical metric names (e.g., `box AP`, `AP50`, `WER`).
- `metrics` table tracks direction (`higher_is_better` / `lower_is_better`).
- Add missing metrics before ingesting data:

```sql
INSERT INTO metrics (name, full_name, direction, description)
VALUES ('WER', 'Word Error Rate', 'lower_is_better', 'Speech recognition metric')
ON CONFLICT (name) DO NOTHING;
```

## Validation Script

Run after any batch insert to audit metric labels and fill gaps. It is a dry
run by default and exits non-zero when it has findings; add `--fix` to apply
the safe automated changes:

```bash
uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py
```

Checks performed:
- Audits metric labels against each leaderboard's allowed metrics
- Normalizes safe metric aliases (`box mAP` → `box AP`, `AP@50` → `AP50`, …)
- Sets missing `best_metric` values

It does not recompute ranks; use `EvaluationService.recalculate_ranks`.

## Artificial Analysis Scores on Hub Model Repos

`backend/scripts/sync_aa_eval_results_prs.py` is a uv script that runs as a
scheduled Hugging Face Job. It ports Artificial Analysis scores for GPQA
Diamond, MMLU-Pro, Terminal-Bench 2.1 and Terminal-Bench 4.0 to open-weight
Hub model repos as `.eval_results/` PRs. It matches each AA model only to an
exact name in its creator's official Hub org, skips gated repos and
ambiguous, dated or quantized matches, and skips benchmarks a repo already
reports on `main` or in an open PR. Dry-run is the default; `--apply` opens
at most `--max-prs` PRs as the token's account.

```bash
env -u HF_TOKEN ARTIFICIAL_ANALYSIS_API_KEY=… uv run --no-project --script backend/scripts/sync_aa_eval_results_prs.py
```

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Evaluation rejected or missing on task leaderboard | Confirm the `(task, dataset)` leaderboard has `task_dataset_metrics` rows and rerun rank recalculation: `EvaluationService.recalculate_ranks(task_id, dataset_id)`. |
| Rankings reversed (higher WER looks “better”) | Ensure metric direction is set to `lower_is_better` in `metrics` and recalculate ranks. |
| Duplicate evaluation | Update the existing record with `PUT /api/v1/evaluations/{evaluation_id}` instead of posting another row. |
| API 422 validation error | Review fields against `EvaluationCreateRequest` in `backend/models/evaluations.py`. |

## Related Files

- Service layer: `backend/services/dataset_service.py`, `backend/services/evaluation_service.py`, `backend/services/leaderboard_metric_service.py`
- Metric tooling: `backend/database/validate_evaluation_metrics.py`
- Triple reference: `docs/DATABASE_SCHEMA_UML.md` (important invariants)
- Migration convention: `backend/database/migrations/README.md`

_Last updated: 20 October 2026_

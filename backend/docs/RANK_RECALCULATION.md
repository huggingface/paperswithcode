# Evaluation Rank Recalculation

This document describes the automatic rank recalculation system for benchmark evaluation leaderboards.

## Overview

The system automatically recalculates leaderboard ranks whenever evaluation results are added, updated, or deleted. This ensures that ranks always reflect the actual performance ordering based on metric scores.

## How It Works

### Automatic Recalculation

Ranks are automatically recalculated after:
- **Creating** a new evaluation (`POST /api/v1/evaluations/`)
- **Updating** an existing evaluation (`PUT /api/v1/evaluations/{id}`)
- **Deleting** an evaluation (`DELETE /api/v1/evaluations/{id}`)

### Ranking Logic

1. **Grouping**: Evaluations are grouped by:
   - `task_id` + `dataset_id` (defines a leaderboard)
   - `uses_additional_data` (separate rankings for models with/without additional training data)

2. **Sorting**: Within each (task, dataset) group, evaluations are ranked per metric using every row that carries a parseable value for that metric in `metrics` — not only rows whose `best_metric` matches. For example, FPS rank includes mAP-primary detectors that also report throughput. `best_rank` is stored only on rows where `best_metric` equals the metric being ranked.

3. **Tied Ranks**: Evaluations with identical metric values receive the same rank

4. **Missing Metrics**: Evaluations without a valid `best_metric` value receive `NULL` rank

## API Endpoints

### Automatic Recalculation

When you create, update, or delete an evaluation, ranks are automatically recalculated:

```bash
# Create evaluation - ranks auto-calculated
POST /api/v1/evaluations/
{
  "paper_id": 123,
  "task_id": 2,
  "dataset_id": 5,
  "model_name": "YOLOv12",
  "metrics": {"mAP": "68.0"},
  "best_metric": "mAP"
}

# Update evaluation - ranks auto-recalculated
PUT /api/v1/evaluations/456
{
  "metrics": {"mAP": "70.0"}
}
```

### Manual Recalculation

You can manually trigger rank recalculation for a specific leaderboard:

```bash
POST /api/v1/evaluations/recalculate-ranks?task_id=2&dataset_id=5
```

**Response:**
```json
{
  "message": "Successfully recalculated ranks for 10 evaluations",
  "task_id": 2,
  "dataset_id": 5,
  "updated_count": 10
}
```

## Command-Line Tools

### Recalculate All Ranks

To recalculate ranks for all evaluations in the entire database:

```bash
uv run --env-file backend/keys.env backend/scripts/recalculate_all_ranks.py
```

This script:
- Finds all unique task+dataset combinations
- Recalculates ranks for each leaderboard
- Provides progress logging
- Handles errors gracefully

**Output:**
```
2025-10-15 12:00:00 - INFO - Finding all unique task+dataset combinations...
2025-10-15 12:00:00 - INFO - Found 15 unique leaderboards
2025-10-15 12:00:01 - INFO - Recalculating ranks for task_id=2, dataset_id=5 (10 evaluations)...
2025-10-15 12:00:01 - INFO -   Updated 10 evaluations
...
2025-10-15 12:00:05 - INFO - ✓ Successfully updated ranks for 150 evaluations
```

## Testing

Run the test suite to verify rank recalculation works correctly:

```bash
# Using pytest
uv run --env-file backend/keys.env python -m pytest backend/tests/evaluation/test_rank_recalculation.py -v

# Or run manually
uv run --env-file backend/keys.env python backend/tests/evaluation/test_rank_recalculation.py
```

**Tests include:**
- Basic rank calculation
- Rank recalculation on update
- Rank recalculation on delete
- Separate ranking for evaluations with/without additional data

## Example Scenario

### Problem (Before)
```
Leaderboard: COCO test-dev (Object Detection)
┌─────┬────────────┬──────┬──────┐
│ Rank│ Model      │ mAP  │ Year │
├─────┼────────────┼──────┼──────┤
│  6  │ CoDETR     │ 65.90│ 2022 │  ← Highest score but wrong rank!
│  1  │ YOLOv12    │ 60.50│ 2025 │  ← Lower score but rank 1?
└─────┴────────────┴──────┴──────┘
```

### Solution (After)
```
Leaderboard: COCO test-dev (Object Detection)
┌─────┬────────────┬──────┬──────┐
│ Rank│ Model      │ mAP  │ Year │
├─────┼────────────┼──────┼──────┤
│  1  │ CoDETR     │ 65.90│ 2022 │  ✓ Correct!
│  2  │ YOLOv12    │ 60.50│ 2025 │  ✓ Correct!
└─────┴────────────┴──────┴──────┘
```

When you add a new model:
```bash
POST /api/v1/evaluations/
{
  "model_name": "DETR-X",
  "metrics": {"mAP": "70.0"},
  "best_metric": "mAP",
  ...
}
```

Ranks automatically update:
```
┌─────┬────────────┬──────┬──────┐
│  1  │ DETR-X     │ 70.00│ 2025 │  ✓ New #1!
│  2  │ CoDETR     │ 65.90│ 2022 │  ✓ Moved to #2
│  3  │ YOLOv12    │ 60.50│ 2025 │  ✓ Moved to #3
└─────┴────────────┴──────┴──────┘
```

## Implementation Details

### Service Method

The `EvaluationService.recalculate_ranks()` method in `backend/services/evaluation_service.py`:

```python
def recalculate_ranks(
    self,
    task_id: int,
    dataset_id: int,
    uses_additional_data: Optional[bool] = None,
) -> int:
    """
    Recalculate ranks for all evaluations in a specific leaderboard.

    Returns:
        Number of evaluations updated
    """
```

### Database Schema

The `evaluations` table includes:
- `best_rank` (INTEGER, nullable): The calculated rank
- `best_metric` (VARCHAR(100)): Name of the metric used for ranking (e.g., "mAP", "AP")
- `metrics` (JSONB): All metric values (e.g., {"mAP": "65.90", "AP50": "80.5"})

### Ranking Algorithm

```python
# 1. Group evaluations by task_id + dataset_id + uses_additional_data
# 2. Extract metric values from the JSONB metrics field using best_metric
# 3. Sort by metric value (descending - higher is better)
# 4. Assign ranks:
#    - Same score = same rank
#    - NULL/invalid metrics = NULL rank
# 5. Commit all updates to database
```

## Migration

To update existing evaluations with correct ranks:

```bash
# Recalculate all ranks in the database
uv run --env-file backend/keys.env backend/scripts/recalculate_all_ranks.py
```

This is safe to run multiple times and can be used after data imports or manual corrections.

## Troubleshooting

### Ranks not updating?

1. Check that `best_metric` is set correctly:
   ```sql
   SELECT id, model_name, best_metric, metrics
   FROM evaluations
   WHERE task_id = X AND dataset_id = Y;
   ```

2. Verify the metric exists in the `metrics` JSONB:
   ```sql
   SELECT id, model_name, metrics->>'mAP' as map_value
   FROM evaluations
   WHERE best_metric = 'mAP';
   ```

3. Manually trigger recalculation:
   ```bash
   POST /api/v1/evaluations/recalculate-ranks?task_id=X&dataset_id=Y
   ```

### Invalid metric values?

Metric values must be numeric (convertible to float). If conversion fails, the evaluation gets `NULL` rank.

### Separate rankings?

Evaluations are ranked separately based on `uses_additional_data`. To see both groups:
```bash
# Without additional data
GET /api/v1/evaluations/?task_id=X&dataset_id=Y&uses_additional_data=false

# With additional data
GET /api/v1/evaluations/?task_id=X&dataset_id=Y&uses_additional_data=true
```

## Future Enhancements

- Support for "lower is better" metrics (e.g., error rates)
- Configurable ranking direction per metric
- Bulk recalculation API for multiple leaderboards
- Background task for periodic rank verification

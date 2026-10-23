---
name: add-benchmark
description: Add or update benchmark datasets/leaderboards in the paperswithcode repo database. Use this whenever the user asks to add a benchmark, add a leaderboard, set default/featured benchmarks for a task, link benchmarks to tasks, add Accuracy or other metrics for a benchmark, or fix benchmark source links. This is repo-specific and should trigger even if the user only names benchmark titles and a task page.
---

# Add a benchmark

This skill adds benchmark metadata in the database so task pages, benchmark pages, and the benchmark source paper page render correctly.

## Core rule

Benchmark source links must be native Papers with Code paper URLs:

```text
https://paperswithcode.co/paper/{arxiv_id}
```

For external non-ArXiv source papers, use the local external paper route:

```text
https://paperswithcode.co/paper/{paper_id}
```

Do not leave `datasets.paper_url` pointing to arXiv, OpenReview, a PDF, a project page, DOI page, or vendor blog when the benchmark has a source paper. First find or create the local `papers` row, set `datasets.introducing_paper_id`, then set `datasets.paper_url` to the native local paper URL. If you cannot identify a source paper that can become a local paper page, stop and ask the user for the missing source details instead of inventing or storing an external source.

Be careful about provenance: the benchmark source paper is the paper that introduced or formally describes the benchmark/dataset, not a later model paper that merely evaluates on it. If a result paper cites a benchmark source, follow that citation and use the cited source paper for `datasets.introducing_paper_id` / `paper_url`. Use the result paper only when it truly introduces a new benchmark, split, evaluation set, or leaderboard definition.

## Workflow

1. Identify the target task:
   - Prefer the URL slug the user gave, such as `/tasks/agents`.
   - Query `tasks` by `slug` and nearby names if needed.

2. Check whether each benchmark already exists:
   - Search `datasets` by exact name, slug, and fuzzy name variants.
   - Reuse an existing row when it clearly represents the requested benchmark/version.
   - Create a new `datasets` row only when no good match exists.

3. Normalize the source paper:
   - Resolve the source paper from the user-provided source, benchmark homepage, public paper page, or the citation in the model/result paper that uses the benchmark.
   - Check whether the candidate source actually introduced/described the benchmark. Do not use a paper just because it reports scores on the benchmark.
   - If the source has an arXiv ID, find the local paper row in `papers` by `arxiv_id`; if it is missing, index/import it using existing repo tooling.
   - If the source is a non-ArXiv paper, DOI, technical demo, proceedings paper, benchmark website, or report, create or reuse an external `papers` row with `source = 'external'`, canonical `source_url`, title, authors, abstract/summary, and `date_published`.
   - Update the dataset with:
     - `introducing_paper_id = papers.id`
     - `introducing_paper_title = papers.title`
     - `paper_url = 'https://paperswithcode.co/paper/' || papers.arxiv_id` for ArXiv rows
     - `paper_url = 'https://paperswithcode.co/paper/' || papers.id` for external rows

4. Tag the source paper:
   - Ensure the benchmark's introducing paper is linked to the relevant task in `paper_tasks`.
   - Use `source = 'manual'` for these task links so keyword rebuilds do not remove them.
   - If the source paper introduces or clearly uses methods that already exist in `methods`, ensure `(paper_id, method_id)` exists in `paper_methods`.
   - Do not invent vague methods just to fill the page. Add method links only when the match is clear from the paper title/abstract/source or from an existing canonical method row.
   - Preserve unrelated existing paper task/method links; only add missing links unless the user explicitly asks to retag the paper.

5. Link the benchmark to the task:
   - One benchmark has one leaderboard per metric, on one task. Before linking an existing dataset to another task, check where its evaluations live (`SELECT task_id, best_metric, count(*) FROM evaluations WHERE dataset_id = :id GROUP BY 1, 2`). If the requested metric already has a leaderboard on another task, do not link it a second time: use that task, or create a renamed benchmark variant when the new task measures a different protocol (for example `ImageNet (256x256)` for image generation, because `ImageNet` is the image classification board). The database rejects evaluations that would split a leaderboard (`evaluations_single_benchmark_board`); record a genuine same-metric exception in `benchmark_task_board_exceptions` only when the user approves it.
   - Ensure `(task_id, dataset_id)` exists in `task_datasets`.
   - Benchmark display order is derived from the benchmark trending signal; do not add manual ordering metadata.

6. Link metrics:
   - Use the requested metric, often `Accuracy`.
   - Ensure `(task_id, dataset_id, metric_id)` exists in `task_dataset_metrics`.
   - Do not duplicate metrics that are already present.

7. Verify:
   - Query the ranked task benchmarks from `task_datasets`.
   - Query `paper_tasks` and `paper_methods` for every source paper touched.
   - Query the dataset rows and confirm `paper_url` starts with `https://paperswithcode.co/paper/` and points to the actual introducing/descriptive source paper, not merely a later evaluation paper.
   - Hit the relevant API endpoint when the app is running, for example:

```bash
uv run --env-file backend/keys.env python - <<'PY'
import json
from urllib.request import urlopen

with urlopen("https://paperswithcode.co/api/v1/datasets/?task=agents&page_size=5&ordering=-paper_count") as resp:
    payload = json.load(resp)

for dataset in payload["results"]:
    print(dataset["name"], dataset["paper_url"])
PY
```

## Database access

Run Python with the repo environment:

```bash
uv run --env-file backend/keys.env python ...
```

Use SQLAlchemy through `backend.database.connection.get_engine()` for idempotent updates. Prefer `INSERT ... ON CONFLICT DO NOTHING/UPDATE` for `paper_tasks`, `paper_methods`, `task_datasets`, and `task_dataset_metrics`.

When linking a benchmark to a task:

```python
session.execute(
    text(
        """
        INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
        VALUES (:t, :d, FALSE)
        ON CONFLICT (task_id, dataset_id) DO NOTHING
        """
    ),
    {"t": task_id, "d": dataset_id},
)
```

## Reporting back

Report which benchmarks already existed, which were created, which metric was linked, which source-paper task/method tags were added, and the final native source URL for each benchmark. Mention when a tempting result paper was deliberately not used because it only evaluated on or cited the benchmark. If any source paper cannot be resolved to a native local paper URL, clearly list what information is needed from the user.

**Always end with the benchmark page URL(s)** so the user can open them directly:

```text
https://paperswithcode.co/benchmark/{dataset_slug}
```

Use the `datasets.slug` value (from the created or reused row). When a benchmark is task-scoped, you may append `?task={task_slug}` for the task-filtered leaderboard view, but the bare `/benchmark/{slug}` URL is sufficient by default.

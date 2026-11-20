# ADR 0003: Evaluations, benchmarks and leaderboards

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## Benchmark gap candidate review times use the database clock

BenchmarkCurationCandidate.reviewed_at is set with func.now() so it shares the database clock with the created_at of curation jobs queued in the same transaction. handle_terminal_job counts failed creation jobs since the current approval by comparing those two timestamps in SQL; mixing application and database clocks would miscount failures after each re-approval.

Code: `backend/services/benchmark_gap_review_service.py::BenchmarkGapReviewService.apply_review`, `backend/services/benchmark_gap_review_service.py::BenchmarkGapReviewService.apply_add_benchmark`, `backend/services/benchmark_gap_review_service.py::BenchmarkGapReviewService.handle_terminal_job`

## Benchmark gap candidates are locked in identity-key order

Concurrent gap-review jobs that report the same benchmarks lock BenchmarkCurationCandidate rows with SELECT FOR UPDATE. Rows are locked in sorted identity_key order so two jobs cannot deadlock by acquiring the same rows in different orders; results are still returned in the agent's original gap order.

Code: `backend/services/benchmark_gap_service.py::BenchmarkGapService.persist`

## Benchmark gap review jobs must decide every candidate in their scope

A review-benchmark-gaps curation job is served a fixed batch of candidate ids, persisted in review_scope. The job is required to record a decision for every id in that scope; the scope is what completion is checked against.

Code: `backend/models/database/curation.py::PaperCurationJob.review_scope`

## Benchmark paper_count counts logical leaderboard rows

The public `paper_count` field on dataset listings keeps its legacy name but means leaderboard entry count: distinct (paper, task, dataset, model, harness) groups. This matches the row count the benchmark page renders after merging per-metric evaluation records, so one model evaluated on four metrics counts as one entry, not four.

Code: `backend/services/dataset_service.py::DatasetService.get_datasets`

## Benchmark popularity ordering counts the whole evaluations table

Ordering evaluations by benchmark_popularity uses the total number of evaluation rows on each dataset across the entire table, computed in a joined subquery. A subquery keeps the per-evaluation result set (no outer GROUP BY) and makes popularity independent of the caller's filters, so a benchmark's popularity does not change with the search or page.

Code: `backend/services/evaluation_service.py::EvaluationService.get_evaluations`

## Benchmark task membership comes from task_datasets

Dataset listings filter by task through the task_datasets association, not through per-metric leaderboard triples or evaluations, so display membership stays independent of which metrics are configured. With include_descendants the filter expands to all subtasks so parent task pages roll up child-task benchmarks.

Code: `backend/services/dataset_service.py::DatasetService.get_datasets`

## Benchmark variant names carry their qualifier in trailing parentheses

The task page groups variant benchmarks under their parent board and labels each chip with the qualifiers the variant name adds in parentheses (frontend/src/lib/benchmarkVariants.ts variantLabel). Variant dataset names must therefore end in '(<qualifier>)', e.g. 'Open TTS Leaderboard (12-language average)'; renaming a variant without that suffix yields an unlabelled or wrong chip.

Code: `backend/database/datasets_setup/add_open_tts_leaderboard.py::ALL_LANGUAGE_NAME`

## Creation context exposes the evidence consensus the apply step accepts

The add-benchmark creation context lists the evidence consensus (leading task ids and primary metrics). apply_add_benchmark accepts choices within that consensus without a *_choice_reason and requires an explicit reason for anything else, so the two must stay aligned.

Code: `backend/services/benchmark_gap_review_service.py::BenchmarkGapReviewService.creation_context`

## Evaluation harness is stored separately from model_name

Agentic benchmarks such as Terminal-Bench score a model plus a harness (e.g. Claude Code, Terminus). Evaluations store the harness in its own nullable harness column instead of folding it into model_name, so leaderboards can render and group model and harness separately. Importers must put the harness there, not in the model name.

Code: `backend/models/database/evaluations.py::Evaluation.harness`

## Evaluation serialization preloads papers into the session identity map

_serialize_evaluations loads all referenced source papers in one query and holds them in a dict, keeping them in the SQLAlchemy identity map. URL helpers such as evaluation_public_source_url then use db.get, which returns identity-mapped objects without a query. Replacing db.get with a filtered query, or dropping the held dict, reintroduces one query per evaluation.

Code: `backend/services/evaluation_service.py::evaluation_public_source_url`, `backend/services/evaluation_service.py::EvaluationService._serialize_evaluations`

## Files inside a paper's linked repositories count as first-party sources

When checking whether an evaluation's source URL belongs to its paper, reports, result files and READMEs inside a linked GitHub repository or Hugging Face model, dataset or Space repository are treated as first-party evidence. Source match keys collapse a repository root and every file below it to one repository key, while different repositories and different Hugging Face repository kinds stay distinct.

Code: `backend/services/evaluation_service.py::_source_match_keys`

## Gap candidates fall back to a same-name match for pre-v2 keys

Candidates created before the v2 identity key hashed the evidence URL, so their identity_key does not match newly computed keys. When no row matches the new key, persist reuses a candidate of the same gap type whose normalised canonical name matches, and rewrites its identity_key, so later papers keep aggregating onto the existing candidate instead of creating duplicates.

Code: `backend/services/benchmark_gap_service.py::BenchmarkGapService.persist`

## Gap review batches are capped to fit the 20-minute Codex run

The remote runner gives the Codex overseer 20 minutes per job, so a review job serves at most 150 benchmark gap candidates (REVIEW_BATCH_LIMIT). Raising it risks the overseer running out of time before deciding on its batch.

Code: `backend/services/benchmark_gap_review_service.py::REVIEW_BATCH_LIMIT`

## Gap review batches are frozen on first read under a row lock

A review job's candidate batch is computed and stored in review_scope on the first context read, with the job row locked FOR UPDATE and re-checked, so overlapping first reads record a single batch. Later reads serve the frozen batch so the overseer's decisions match what it was shown.

Code: `backend/services/benchmark_gap_review_service.py::BenchmarkGapReviewService.review_context`

## Harness support is unscoped when rolling up descendant tasks

Whether a leaderboard allows harness values is configured on the owning task. When a parent task page rolls up descendant benchmarks, the harness lookup drops task scoping and reports whether any leaderboard on the dataset allows harness values; scoping to the parent would wrongly report no support.

Code: `backend/services/dataset_service.py::DatasetService.get_datasets`

## Leaderboard parameter filtering is per entry and computed in SQL

Parameter counts belong to a displayed leaderboard entry (the frontend's grouping of sibling metric rows), not to individual metric rows. get_evaluations computes parameter coverage in SQL so ordinary paginated queries stay bounded. Only an explicit max_parameters_exclusive bound materializes all entries in Python to filter them; ordinary queries keep the established row-level pagination contract.

Code: `backend/services/evaluation_service.py::EvaluationService.get_evaluations`

## Leaderboards keep one entry per model across twin papers

A model may already appear on a leaderboard via a twin paper, such as an external release page or an older arXiv version. Curation checks find_leaderboard_duplicate and leaves the existing row, reporting a skip, so a leaderboard keeps one entry per model.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService._apply_evaluations`

## Metrics named Overall sort first on multi-metric leaderboards

Leaderboard metrics are ordered with any metric whose name contains "overall" first, then alphabetically. The frontend defaults to the first metric, so multi-metric benchmarks open on their headline score rather than an alphabetically earlier side metric.

Code: `backend/services/leaderboard_metric_service.py::LeaderboardMetricService.get_leaderboard_metrics`

## OpenReview URLs normalize to the submission id

OpenReview serves the same submission at /forum?id=... and /pdf?id=..., so URL normalization treats both as one key built from the id query parameter. The query cannot simply be dropped like other tracking parameters, because every OpenReview paper would then collapse to the same host/path key and match each other.

Code: `backend/services/evaluation_service.py::_normalize_url_for_match`

## Rank refresh flushes explicitly because sessions disable autoflush

Database sessions are created with autoflush=False, so rank updates made by recalculate_ranks with commit=False are not visible to later queries until flushed. refresh_rank_scopes ends with an explicit db.flush(), which callers rely on before audit snapshots and reloads. Removing it makes subsequent reads see stale ranks.

Code: `backend/services/evaluation_service.py::EvaluationService.refresh_rank_scopes`

## Rejected benchmark candidates reopen when evidence doubles

When a benchmark gap candidate is rejected, its distinct paper count is stored in reviewed_paper_count. The candidate re-enters review only once its paper count reaches twice that value, avoiding re-review churn from marginal new evidence.

Code: `backend/models/database/curation.py::BenchmarkCurationCandidate.reviewed_paper_count`

## Reports on merged gap candidates follow merged_into_id

A reviewed duplicate candidate keeps its own identity_key but records merged_into_id. New reports that match it follow the merged_into_id chain and attach to the surviving candidate, so review merges are not undone by later agent reports.

Code: `backend/services/benchmark_gap_service.py::BenchmarkGapService.persist`

## Sparse benchmarks are hidden from task lists via HAVING

Task-page benchmark lists hide benchmarks with fewer logical leaderboard rows than min_eval_count using a HAVING on the same aggregate, without touching data. Living external leaderboards are exempt, and the dataset detail page loads by slug and bypasses this filter, so hidden benchmarks remain reachable.

Code: `backend/services/dataset_service.py::DatasetService.get_datasets`

## Task-scoped benchmark counts only include that task's evaluations

One dataset can host separate leaderboards for different tasks (for example supervised video segmentation versus unsupervised VIS). When a task filter is active, the evaluation join is restricted to the task (and descendants when requested) so counts reflect that task's leaderboard rather than every row on the shared dataset.

Code: `backend/services/dataset_service.py::DatasetService.get_datasets`

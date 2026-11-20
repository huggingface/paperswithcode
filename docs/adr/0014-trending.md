# ADR 0014: Trending scores

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## Catalog monthly paper counts are cached for five minutes

Every method trend normalizes by catalog-wide monthly paper counts, which are identical across methods and require a full scan of the papers table. They are cached in-process for 300 seconds and shared across requests so a burst of trend pages does not repeat the scan.

Code: `backend/services/method_trend_service.py::CATALOG_MONTH_COUNTS_TTL_SECONDS`

## Composite paper trending score sits behind PWC_TRENDING_RANKING_MODE

papers.trending_score combines GitHub star velocity with Hugging Face artifact trending and is computed by the calculate_paper_trending_scores cron. The public feed only ranks by it when PWC_TRENDING_RANKING_MODE=composite; the default github mode reads repositories.trending_score. The cron keeps the column populated even while unused so switching modes is an instant, data-free rollback.

Code: `backend/models/database/papers.py::Paper.trending_score`

## Explicit flush before the rolling trending average

Repository sessions are created with autoflush disabled, so today's snapshot upserts would not be visible to the rolling 30-day average query in the same transaction. calculate() flushes explicitly before running that query; removing the flush computes averages without today's scores.

Code: `backend/services/organization_trending_service.py::OrganizationTrendingService.calculate`

## HF artifacts linked to more than five papers are aggregators

A paper's own Hugging Face artifact is linked to a handful of papers; live trending models were observed never to exceed 5 linked papers, while aggregator Spaces and datasets reach thousands. HF_MAX_ARTIFACT_PAPERS = 5 is the cutoff above which an artifact counts for nothing in trending scores.

Code: `backend/utils/trending.py`

## Method trends count papers per day in SQL without DISTINCT

paper_methods is unique per (paper, method), so joining it to papers yields each paper once and no DISTINCT is needed. Aggregating counts per publication day in PostgreSQL keeps popular methods from shipping tens of thousands of rows to Python.

Code: `backend/services/method_trend_service.py::MethodTrendService.get_method_trend`

## Methods can override the start month of their usage trend

Method.trend_start_date optionally sets the first month of a method's usage trend and of its reference backfill. It exists for methods whose source paper or introduced year is later than the field actually started, so the trend is not truncated at the source year.

Code: `backend/models/database/taxonomy.py::Method`

## Paper trending shows at most one paper per GitHub repository

When several latest-version papers share a GitHub repository (for example an older and a newer paper pointing at the same repo), the trending feed keeps only the most recently published one, using a PARTITION BY repository_id rank. This prevents one repository from occupying several trending slots.

Code: `backend/tests/paper/test_feed_filters.py::test_trending_endpoint_deduplicates_view_rows_by_paper`

## Public trending feed defaults to GitHub star velocity; composite is opt-in

The papers feed can rank by official GitHub repository star velocity or by the composite papers.trending_score (GitHub velocity plus Hugging Face artifact trending, computed by calculate_paper_trending_scores). GitHub velocity stays the default so that unsetting PWC_TRENDING_RANKING_MODE is an instant rollback; operators switch to composite with PWC_TRENDING_RANKING_MODE=composite.

Code: `backend/config.py::Settings.trending_ranking_mode`

## Reference backfill restarts a month when papers land behind its cursor

The method reference backfill walks each month with a stable (published, id) tuple cursor. If a paper is imported behind the cursor while the month is running, the month finishes with fewer accounted papers than eligible; it is reset to pending and rerun from the start. This is safe because link writes are idempotent and each month is bounded.

Code: `backend/services/method_backfill_service.py::run_reference_backfill`

## Share-lift ranking filters the time window in WHERE

Share-lift ranking restricts to latest-version arXiv papers published between the baseline start and today in the WHERE clause rather than inside the CASE aggregates. This lets Postgres skip most of papers and the junction rows before aggregation.

Code: `backend/services/share_lift.py::rank_by_share_lift`

## Share-lift scores are computed in SQL

share_lift = (recent * all_baseline) / (baseline * all_recent) and the trend score are computed in SQL so Postgres can filter, sort and LIMIT server-side. The corpus totals are known non-zero, the min_baseline_papers gate (>= 1) guarantees a non-zero baseline count, and casts force float division.

Code: `backend/services/share_lift.py::rank_by_share_lift`

## Stored trending scores are compared with a tolerance

Stored trending scores and components are rounded to 4 decimals before writing, so comparisons between a stored score and a recomputed base use STORED_SCORE_TOLERANCE (0.02) to avoid treating rounding noise as an editorial boost.

Code: `backend/utils/trending.py`

## Trending feed dedupes papers by official repository

The global trending feed ranks papers either by papers.trending_score (GitHub star velocity plus Hugging Face artifact trending, computed by the calculate_paper_trending_scores CRON) or, as the rollback path, by GitHub EMA star velocity alone. Both queries pick each paper's best official repository and keep only the most recently published paper per repository, so the feed never shows duplicate repo cards. Papers with only an HF signal have a NULL repository_id and are never collapsed together. Repository-scoped feeds skip this dedup and list every linked paper.

Code: `backend/services/paper_service.py::PaperService.get_papers`, `backend/services/paper_service.py::PaperService._TRENDING_SQL_GITHUB`, `backend/services/paper_service.py::PaperService._TRENDING_SQL_COMPOSITE`

## Trending methods use a 10-minute process cache

The methods directory requests the same trending ranking on every visit while the underlying papers change only with daily imports. A short shared in-process cache (600 seconds) avoids recomputing the ranking per request while staying effectively current.

Code: `backend/services/method_service.py::TRENDING_METHODS_TTL_SECONDS`

## Trending scores expire after 24 hours

Repository and paper trending scores whose timestamp is older than 24 hours are treated as missing by the trending sort, so stale scores never rank a paper. Fixtures and backfills must stamp a fresh timestamp for a score to count.

Code: `backend/tests/taxonomy/test_tasks_api.py::_FRESH`

## Trending tasks and methods count only arXiv papers

Share-lift trending for tasks and methods compares each entity's share of recent papers with its share in a baseline window. External papers arrive in bulk backfills that would dilute baseline shares, so the window predicate in rank_by_share_lift counts only latest-version source='arxiv' papers.

Code: `backend/tests/taxonomy/test_trending_taxonomy_api.py::test_trending_ignores_external_papers`

## Trending tasks are cached in-process for 10 minutes

Trending task domains depend only on date windows and request filters, yet the homepage requests the same ranking on every visit. Papers arrive through daily imports, so a shared 600-second in-process cache avoids recomputing the expensive ranking while keeping it effectively current.

Code: `backend/services/task_service.py::TRENDING_TASKS_TTL_SECONDS`

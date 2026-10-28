# Independent data-plane probes

This reference describes the current production contracts. Discover job IDs dynamically from the active release, then use the matching section. If the registry contains an ID without a section, inspect its deployed workflow, script, services, and persistence models; mark probe coverage drift rather than skipping it.

For each job, retain bounded evidence: cohort size, missing/stale/error counts, oldest or percentile age, a deterministic recomputation or upstream sample, and one user-visible read where applicable. Dashboard freshness queries are useful baselines but are not independent proof.

## Shared leaderboard sync procedure

For every managed leaderboard sync, fetch the current upstream source read-only and independently normalize its row keys. Compare the complete bounded set when feasible, otherwise a stratified sample plus set/count aggregates. Verify model/release identity, metric values and units, evaluation date/harness/source, expected dataset, managed methodology, row ownership, stale-row deletion, preservation of unrelated manual rows, rank direction, ties, and the public benchmark API. A recent `evaluations.updated_at` only proves rows were touched.

## `paper_markdown_backfill`

- **Effect:** Creates/copies paper Markdown objects and `_jobs/status/*.json` plus coverage/progress records in the paper-Markdown Hugging Face bucket; may launch OCR jobs.
- **Lanes:** hourly live (14 days, minus the last 24 h) and full lanes share the `paper_markdown_backfill` lock; the 5-minute fresh lane (`--lane fresh`, `pwc-cron-paper-markdown-fresh.timer`, lock `paper_markdown_backfill.fresh`) owns papers indexed in the last 24 h and labels its HF jobs `mode=live, lane=fresh`. A paper older than an hour with no layout in `huggingface/pwc-papers-pages` means the fresh lane is stuck (check its HF jobs for SCHEDULING stalls).
- **Independent proof:** Anti-join all latest arXiv papers—and recent 14-day papers separately—against expected object keys. Classify missing, invalid, empty, oversized, failed, interrupted, and unresolved-volume-mount states. Inspect coverage-history movement and orphan keys.
- **Correctness:** Decode a stratified sample and verify nontrivial text, title/arXiv identity, version, and absence of obvious OCR/error payloads. Key existence alone is insufficient.

## `update_hot_github_trending`

- **Effect:** Refreshes 0–30-day official repositories, star history, repository EMA trending, and linked recent paper trending components/scores.
- **Independent proof:** Reconstruct eligible hot repo groups; measure queue coverage, oldest wait, one-snapshot starvation, and linked stale paper scores. The dashboard's oldest wait uses the later of the latest snapshot and `num_stars_updated_at`, because terminal 404/451 repositories get no snapshot but are re-checked like any other. Compare sampled GitHub `stargazers_count` to repository values and latest star-history rows.
- **Correctness:** Recompute repository EMA and paper composite scores from durable inputs; compare exact or tolerance-bounded results and public trending ordering.

## `update_github_stars`

- **Effect:** Refreshes `repositories.num_stars`, `num_stars_updated_at`, and `repository_star_history` for 31–180-day hourly and older weekly queues.
- **Independent proof:** Partition eligibility by queue, inspect age distribution and oldest wait, and ensure duplicate owner/name records agree. Compare a stratified GitHub API sample with stored stars and latest snapshots; inspect implausible deltas.
- **Trap:** Terminal 404/451 handling may advance a checked timestamp without changing stars. Count these separately from successful refreshes.

## `update_citations`

- **Effect:** Updates paper citation count, Semantic Scholar ID, and `citation_updated_at` across cadence buckets.
- **Independent proof:** Reconstruct eligible/backlog buckets and their age distribution. Compare a bounded stratified sample directly with Semantic Scholar using stable paper identity; verify the stored ID and count.
- **Correctness:** Flag suspicious mass zeroing/decreases and timestamps advanced after not-found/error outcomes. A fresh maximum timestamp is weak evidence. The dashboard degrades on Semantic Scholar throttling only when `rate_limit_hits` reach 5% of `api_calls`; a handful of retried 429s is routine.

## `extract_urls`

- **Effect:** Manual/paused pipeline marks `urls_extracted` and writes official repositories/project pages plus junctions.
- **Independent proof:** Report schedule as `not_applicable`. If auditing a claimed dispatch, measure unresolved backlog and false-complete papers with no official resource; sample linked URLs for HTTP reachability, canonical GitHub identity, and officialness.
- **Safety:** Do not invoke select/discover/persist to test health.
- **Dashboard freshness:** the newest `repositories` / `project_pages` row with `source = 'ai_extraction'`, stale after seven days; `papers.updated_at` moves for every catalog edit and proves nothing about this pipeline.

## `calculate_trending_scores`

- **Effect:** Computes repository trending score/timestamp from star-history snapshots.
- **Independent proof:** Recompute the deployed EMA/clamps for a stratified sample or full bounded SQL cohort; compare exact/tolerance-bounded values, eligible stale backlog, and timestamp coverage.
- **Correctness:** Check negative, non-finite, and extreme outliers plus distribution shifts. Fresh rewrites can conceal a broken formula.

## `calculate_paper_trending_scores`

- **Effect:** Computes paper total, GitHub, and Hugging Face trending components, clears stale values, and applies configured pins.
- **Independent proof:** Recompute from fresh official repository scores and linked HF artifacts using deployed normalization/pin rules. Check population coverage, stale clearing, exact sampled scores, and dependency freshness.
- **Functional proof:** Compare public trending API/page order with the recomputed top cohort.

## `update_hf_artifacts`

- **Effect:** Upserts HF artifact identity/metrics, synchronizes exact paper-artifact junctions, and advances paper scan markers; stale links can be deleted.
- **Independent proof:** For recent papers, compare explicit artifacts and HF `arxiv/{id}/repos` results with junction sets. Sample Hub artifact metrics exactly; inspect discovery/refresh backlog age, dangling/duplicate links, and empty scans.
- **Trap:** A fresh `hf_artifacts_scanned_at` can hide missing links or provider-wide empty results.

## `sync_3d_arena`

- **Contract:** `3d-arena-iso3d-living`, `Elo (live, external)`, official 3D Arena HF Space; typically 15–100 rows.
- **Proof:** Apply the shared leaderboard procedure; compare normalized model/paper identity and Elo values, managed row set, ranks, and public API.

## `sync_tabarena`

- **Contract:** `tabarena-v0-1`, `Elo`, official TabArena HF CSV; typically 50–200 rows.
- **Proof:** Apply the shared leaderboard procedure, including complete upstream-vs-owned-row set comparison and rank recomputation.

## `sync_open_asr`

- **Contract:** `open-asr-leaderboard`, WER plus optional RTFx, official HF Space; typically 40–150 rows.
- **Proof:** Apply the shared procedure; verify lower-is-better WER ranking, units, optional RTFx mapping, and managed methodology.

## `sync_mmteb_overall`

- **Contract:** `embedding-models` / `mmteb-v2`, `MMTEB Score`, official MMTEB v2 source, and only rows with the managed MMTEB methodology.
- **Proof:** Apply the shared procedure to the complete overall cohort. Verify model identity, unique contiguous ranks, finite scores, managed-row ownership, and the public embedding-models leaderboard read.

## `sync_mmteb_retrieval`

- **Contract:** `retrieval` / `mmteb-v2`, `Retrieval`, official MMTEB v2 source, and only managed MMTEB rows.
- **Proof:** Apply the shared procedure independently of the overall lane. Verify retrieval values are not copied from aggregate scores and compare the owned row set and public retrieval leaderboard.

## `sync_mmteb_reranking`

- **Contract:** `text-reranking` / `mmteb-v2`, `Rerank`, official MMTEB v2 source, and only managed MMTEB rows.
- **Proof:** Apply the shared procedure independently of the other MMTEB lanes. Verify reranking task identity, values, ranks, stale-row removal, and the public text-reranking leaderboard.

## `sync_mmeb_v2`

- **Contract:** `embedding-models` / `mmeb-v2`, `MMEB-v2 Score`, official MMEB source, and only rows with the managed MMEB methodology.
- **Proof:** Apply the shared procedure to the full v2 cohort. Verify version-specific model identity and scores, managed-row ownership, ranks, and the public leaderboard; do not treat v3 freshness as v2 proof.

## `sync_mmeb_v3`

- **Contract:** `embedding-models` / `mmeb-v3`, `MMEB-v3 Score`, official MMEB source, and only rows with the managed MMEB methodology.
- **Proof:** Apply the shared procedure to the full v3 cohort. Verify v3 is not mixed with v2, including dataset, metric, model set, values, ranks, stale-row removal, and the public leaderboard.

## `sync_deepswe`

- **Contract:** `deepswe`, Pass@1, MiniSWE-Agent, DataCurve JSON.
- **Proof:** Apply the shared procedure; specifically verify fraction-to-percent conversion and configuration/model identity.

## `sync_artificial_analysis`

- **Contract:** Intelligence Index and Agentic Index datasets, `Score`, official Artificial Analysis API/model URLs.
- **Proof:** Compare each index independently; prevent cross-index row mixing and verify source URL/model identity.
- **Budget:** The API key allows 100 requests/day (resets ~04:48 UTC); each full fetch costs 4+ requests and `scan_model_releases` shares the key. Check `artificial_analysis_api_quota remaining=` log lines; 429s late in the UTC day mean the budget is overspent.

## `sync_programbench`

- **Contract:** `programbench`; Resolved, Almost Resolved, and Average Test Pass Rate; mini-SWE-agent; typically 15–60 rows.
- **Proof:** Compare the current embedded upstream results and run URLs; verify units, owned row set, and rank semantics.

## `sync_parsebench`

- **Contract:** `parsebench` on task `ocr`; Overall (ParseBench) plus Tables, Charts, Content Faithfulness, Semantic Formatting, Visual Grounding; official `leaderboard.csv` in `run-llama/parsebench`; typically 40–400 upstream rows, of which only reviewed provider labels are published.
- **Proof:** Diff the current CSV against managed rows (model label, six scores, `hf_model_url`); confirm `parsebench_unreviewed` warnings are either mapped or added to the reviewed exclusions; verify stale managed rows were deleted and ranks recomputed on Overall (ParseBench).

## `sync_extractbench`

- **Contract:** `extractbench` on task `document-understanding`; Value F1 plus Word Grounding F1 and Page Grounding F1 (omitted when upstream reports 0.00 for both); official `leaderboard.csv` in `run-llama/ExtractBench`; typically 30–400 upstream rows, of which only reviewed provider labels are published.
- **Proof:** Diff the current CSV against managed rows (model label, three scores); confirm `extractbench_unreviewed` warnings are either mapped or added to the reviewed exclusions; verify stale managed rows were deleted and ranks recomputed on Value F1.

## `sync_vals_finance_agent`

- **Contract:** `finance-agent-v2` on task `agents`; Accuracy (%) 0–100; the single table on https://www.vals.ai/benchmarks/fabv2; typically 40–400 upstream rows, of which only reviewed labels are published (all 78 on 2026-10-16).
- **Proof:** Diff the Vals table against managed rows (label, accuracy at two decimals); confirm `vals_finance_agent_unreviewed` labels get an identity (index the model's paper first), `missing_papers` is empty, and `missing_upstream` rows were investigated (never deleted automatically); verify ranks on Accuracy.

## `sync_surge_chartography`

- **Contract:** `chartography-no-tools` on task `image-understanding`; Pass@1 0–1 (Surge percent / 100); the "Chartography Leaderboard" block on https://surgehq.ai/benchmarks/chartography (fetch with a browser User-Agent); typically 25–400 upstream rows, of which only reviewed labels are published (41 of 42 on 2026-10-17; DeepSeek V4 Flash Vision (experimental) is excluded on purpose).
- **Proof:** Diff the Surge block against managed rows (label, percent at one decimal); confirm `surge_chartography_unreviewed` labels get an identity (index the model's paper first), `missing_papers` is empty, and `missing_upstream` rows were investigated (never deleted automatically); confirm the with-tools `chartography` benchmark was not touched.

## `sync_frontiercs_2`

- **Contract:** `frontiercs-2` on task `coding-agents`; Pass Rate (%) 0–100 (best metric) and FCI (unbounded, Kimi K2.7 = 0); the `MODELS`/`PASS`/`ECI` constants in https://frontier-cs.org/assets/js/fcs2-data.js behind https://frontier-cs.org/#leaderboard; typically 8–200 entries, one per model and harness (14 on 2026-10-26, all reviewed).
- **Proof:** Diff the data file against managed rows (model, harness, pass rate, FCI); confirm `frontiercs_2_unreviewed` names get an identity (index the model's paper first), `missing_papers` is empty, and `missing_upstream` rows were investigated (never deleted automatically); verify ranks on Pass Rate.

## `sync_physics_iq_verified`

- **Contract:** `physics-iq-verified` on task `video-generation`; Physics-IQ Verified Score (I2V) and (V2V), 0–100; Verified table of the official `google-deepmind/physics-IQ-benchmark` README; typically 30–300 upstream rows, of which only reviewed labels are published (33 on 2026-10-13), one per model and track.
- **Proof:** Diff the README table against managed rows (label, track, score at README precision, ± SD, date added); confirm `physics_iq_verified_unreviewed` warnings are either mapped or covered by the exclusion rules, `missing_papers` is empty, and `missing_upstream` rows were investigated (they are never deleted automatically); verify ranks on both metrics.

## `sync_frontiercode`

- **Contract:** `frontiercode-main` and `frontiercode-extended`; Score and Pass Rate; official Cognition JSON.
- **Proof:** Verify subset assignment, expected test sizes (currently 100/150), model set, values, stale-row deletion, and ranks.

## `sync_coarena`

- **Contract:** `coarena`, `Elo (live, external)`, official CoArena API; typically 5–100 valid rows.
- **Proof:** Filter exactly the deployed valid rating statuses, then apply the shared set/value/rank comparison.

## `sync_arc_prize`

- **Contract:** `arc-agi`, `arc-agi-2`, and `arc-agi-3`; Accuracy/Accuracy/RHAE from the official ARC Prize source.
- **Proof:** Compare the expected snapshot per generation and strongest row per paper/release; verify generation-specific metric semantics and stale managed-row removal.

## `import_hf_daily_papers`

- **Effect:** Inserts/updates papers, authors, resources, auto task/method tags, organizations, and version/external-paper merges from HF daily papers.
- **Independent proof:** Fetch complete HF daily cohorts for each day in the rolling seven-day window and anti-join every arXiv ID against latest papers. Inspect per-day missing and duplicate IDs plus error/delta history.
- **Correctness:** Compare title, abstract, date, TLDR, authors, organization attribution, and resources for a stratified sample. A successful no-op requires proven cohort completeness.

## `enqueue_hf_daily_paper_curation`

- **Effect:** Reconciles the rolling HF cohort into versioned workflows and two-stage jobs; downstream jobs mutate enrichments/evaluations and may request thumbnails.
- **Independent proof:** Compare unique rolling cohort to workflows under active policy; inspect missing/duplicate/deferred reasons, queue age, scheduler state, canary, attempts, and terminal outcomes.
- **Correctness:** For completed/satisfied workflows, verify expected paper mutations and proposal/mutation result—not merely workflow creation. Treat failed/partial/deferred counts as findings even if the generic dashboard evaluator ignores them.
- **Dashboard window:** `failed_workflows` / `partial_workflows` count only workflows whose `cohort_date` is in the last seven days, the cohort the enqueuer revisits. Older partials (most are settled validator rejections from the 2026-09-14 backfill week) need a one-off review, not a standing alarm.

## `enqueue_hf_trending_model_curation`

- **Effect:** Discovers trending HF model candidates, advances their resolver states, and may enqueue bounded paper-curation workflows.
- **Independent proof:** Compare a bounded current Hub trending cohort with candidate identities and `last_seen_at`; inspect missing/duplicate candidates, active/resolved/failed states, oldest wait, attempts, and downstream workflow linkage.
- **Correctness:** Sample resolved candidates and verify canonical paper identity plus resulting enrichment. Fresh candidate timestamps alone do not prove resolution or application. The dashboard counts failed candidates seen in the last seven days and failed/partial workflows from the last seven cohort days.

## `discover_x_threads`

- **Effect:** Prints a JSON summary (`papers_scanned`, `papers_matched`, `threads_linked`, `errors`, `matches`) and upserts `paper_x_thread_scans`. Links `paper_x_threads` only when `PWC_X_THREAD_DISCOVERY_APPLY=true`; every link is a `paper_x_threads` catalog mutation event by `x-thread-discovery`. Exits 0 with an `x_thread_discovery_skipped` warning when `X_API_BEARER_TOKEN` is unset, and 1 only when every search failed.
- **Freshness metrics** (dashboard Database Metrics): `last_write` = latest `paper_x_thread_scans.last_scanned_at` (degraded after 25 h without a scan), `linked_papers` = scanned papers with a linked thread. The job prints its JSON summary to stdout only, so the journal shows just start/finish lines; use `--show-candidates` or the scan table for run results.
- **Independent proof:** Open one matched post from the JSON and confirm it is a paper author or the paper's own organization (business-verified account) introducing that paper, never an outside account; with apply on, confirm the paper page's X threads card shows it.
- **Correctness:** `X search HTTP 401/403` means a bad or unentitled token and `429` an exhausted quota (the run stops at the first one). A zero `papers_scanned` means every recent candidate already has threads or used its three scans.

## `link_google_scholar_profiles`

- **Effect:** Checks Wikidata Scholar-ID candidates (P1960) for authors with 3+ papers: each new author once on Semantic Scholar (ORCID / S2 author ID on 15 sampled papers) into `author_google_scholar_candidates`, then spends the SerpAPI searches left this month (minus 10) reading Scholar profiles of S2-matched candidates, largest authors first, and upserts confirmed links into `author_google_scholar_profiles`; never deletes links.
- **Independent proof:** Open a recently linked author (`/api/v1/authors/<id>` → `google_scholar_id`) and its Scholar page; most of the author's PwC papers must be on the profile and the name must fit.
- **Trap:** On the free SerpAPI plan (250 searches/month) most weekly runs read zero profiles: that is healthy, not stalled; `last_profile_read` advances once a month after the quota resets. `PWC_SERPAPI_API_KEY` missing from `production-cron.env` exits 1. Semantic Scholar 429s slow the run (key shared with citations) but are retried.

## `sweep_conference_deadlines` / `refresh_conference_deadlines`

- **Effect:** Each run first collects finished sweeps (Hugging Face Jobs labelled `workflow=conference-deadlines`), validates every per-conference change set and applies the accepted part to `conferences` / `conference_deadlines` as `deadline_agent_create|update` catalog mutation events by `conference-deadline-agent`; then it launches at most one Job (weekly: up to 30 prioritized conferences with 3 retrieval agents; daily: imminent deadlines and overdue top-tier conferences with 1 agent, skipped when a sweep started in the last 20 h). The ledger is `conference_deadline_sweeps` (`running` → `applied` | `failed`, with per-series `results`, `changes_applied`, `cost_usd`). The research itself never runs on the VPS.
- **Freshness metrics** (dashboard Database Metrics, same SQL as `uv run --env-file backend/keys.env python -m backend.scripts.conference_deadlines status`): `last_write` = latest applied sweep, `top_tier_series`, `top_tier_without_upcoming`, `top_tier_overdue` (no upcoming deadline although last cycle's first deadline + one cycle is under 30 days away). Three or more overdue top-tier conferences degrade the job.
- **Independent proof:** Open `https://paperswithcode.co/api/v1/conferences/deadlines` and confirm the flagship series (CVPR, ICML, NeurIPS, ICLR, ACL, EMNLP) have their next edition once its official CFP is out; spot-check one recent change against the source URL stored in the sweep's `results`.
- **Correctness:** `failed` sweeps with `missing_series` mean the Job timed out or crashed (inspect with `hf jobs logs <id>`); `invalid` series mean a change set failed validation; `rejections` list guarded changes (past edition/deadline, implausible shift, no source URL) that need a human via `PUT /api/v1/conferences/{slug}/deadlines`. A missing `PWC_CONFERENCE_DEADLINES_ANTHROPIC_API_KEY` or HF Jobs credential makes the run exit 1 with `SweepConfigurationError`.

## `enqueue_benchmark_gap_review`

- **Effect:** Once per UTC day queues one `review-benchmark-gaps` overseer job when candidates reported by at least three papers are waiting, plus `add-benchmark` jobs for approved candidates up to 20 per day. Both run on the shared curation queue (trigger `benchmark-gap-cron`, at most two active) and respect the scheduler pause; promotions requeue add-evals for the evidence papers. `--status` prints candidate counts by status and today's creation jobs.
- **Independent proof:** Compare `benchmark_curation_candidates` status counts and `reviewed_at` with the latest `review-benchmark-gaps` job's `mutation_result`; open one promoted candidate's `resolution.dataset_id` on the live site and confirm the leaderboard, source paper, and primary metric.
- **Correctness:** A review job that never applies leaves `reviewed_at` stale while eligible candidates exist. Repeated `add-benchmark` failures back a candidate off 3 days, then return it to review after two failures. Roll back a wrong benchmark with `POST /api/v1/admin/codex-curation/jobs/benchmark-candidates/<id>/rollback`.

## `link_abstract_mentions` / `rescan_abstract_mentions`

- **Effect:** Logs `papers rewritten`, `unchanged`, `already current`, and `judge failures`, and replaces `paper_abstract_mentions` rows per paper. The hourly job looks at papers created or updated in the last 3 days whose stored mentions are missing or stale for the current abstract (at most 500 rewritten per run); the nightly `--rescan` re-runs every abstract so catalog changes reach older papers, reusing earlier Jev verdicts for unchanged abstracts. Needs `PWC_OPENROUTER_API_KEY`; exits 1 when it is missing or when every judged paper failed.
- **Independent proof:** `curl https://paperswithcode.co/api/v1/papers/<id>` for a paper imported in the last hour has `abstract_mentions` (spans whose `surface` equals `abstract[start:end]`), unless its abstract names no catalog entry.
- **Correctness:** Judge failures are OpenRouter errors (key, credits, or a 429): those papers stay unlinked and retry next hour. A rescan that rewrites thousands of papers means the catalog or the matching rules changed; check `SELECT judge, count(*) FROM paper_abstract_mentions WHERE created_at > now() - interval '1 day' GROUP BY 1` for the judge share.
- **Dashboard evidence:** latest `paper_abstract_mentions.created_at` and rows written in 3 hours. Quiet hours are healthy (no new abstracts); a full day without writes while HF daily papers were imported is not.

## `judge_research_topics` / `backfill_research_topics`

- **Effect:** Upserts `research_topic_verdicts` (raw Jev score per followed free-text topic and paper; the feed shows scores >= 0.85). The hourly job (:54) judges every paper published in the last 90 days that has no verdict for the current paper card and prompt version against every followed topic, and logs `pairs judged` and `judge failures`. The per-minute `--backfill` job claims followed topics in `research_topics` with `backfill_status` `pending` (or `running` with a claim older than 30 minutes), judges the last 90 days plus the top 500 older papers by dense + lexical recall, and records `backfill_done`/`backfill_total`. Needs `PWC_OPENROUTER_API_KEY`.
- **Independent proof:** `SELECT t.id, t.backfill_status, t.backfill_done, t.backfill_total, count(v.*) FILTER (WHERE v.score >= 0.85) AS hits FROM research_topics t LEFT JOIN research_topic_verdicts v ON v.topic_id = t.id GROUP BY t.id ORDER BY t.id DESC LIMIT 10`; a `done` topic usually has dozens of hits.
- **Correctness:** There is no fallback: failed Jev calls leave pairs unjudged and the next run retries them. A backfill that fails returns to `pending` (retried after 10 minutes) and becomes `failed` after 5 attempts; a user saving the same topic again resets it. Health is broken when a 90-day paper has waited over 6 hours for a verdict on a backfilled followed topic, and degraded when a backfill waits over an hour or gave up.
- **Dashboard evidence:** latest `research_topic_verdicts.judged_at`, verdicts written in 3 hours, `oldest_unjudged_age_minutes`, `oldest_pending_backfill_minutes`, `failed_backfills`. Hours without followed topics or new papers write nothing and are healthy.

## `warm_paper_suggested_questions`

- **Effect:** Prints a JSON summary (`candidates`, `already_stored`, `generated`, `failed`, `remaining`) and inserts `paper_suggested_questions` rows. Candidates are the home feed's first three trending pages (past week) plus the first trending page of every task and method; `remaining` is the eligible backlog beyond `--limit`. Exits 1 only when every generation failed.
- **Independent proof:** `curl https://paperswithcode.co/api/v1/papers/<id>/suggested-questions` for a top home-feed paper returns three questions within ~0.2 s (stored, not generated).
- **Correctness:** `remaining` should reach 0 after a few runs and stay near 0; a persistent `failed` count with `suggested_questions_failed` warnings means OpenAI errors (key, quota, or model name).
- **Dashboard evidence:** `visible_missing` of `visible_papers` = the top 90 trending latest papers of the past week (an approximation of the home feed's three pages) without a `paper_suggested_questions` row. Zero is healthy even with no recent writes; more than 5 degrades. The task/method part of the cohort needs the probe above.

## `post_trending_paper_to_x`

- **Effect:** Prints a JSON summary (`paper_id`, `text`, `url`, `post_id`, `reply_id`, `errors`) and inserts one `paper_x_posts` row per post. Posts at most one paper per run: the top `trending_score` arXiv paper from the last 14 days with a TL;DR that was never posted. Exits 0 with an `x_trending_post_skipped` warning (dry run) when the `X_POST_*` OAuth 1.0a keys are unset, and 1 only when candidates existed but none could be fetched and rendered.
- **Independent proof:** Open `https://x.com/i/status/<post_id>` and confirm the first-page image, title, TL;DR, and the paper link reply.
- **Correctness:** `X HTTP 401` means bad keys, `403` a read-only app or a post over the account's length limit (`PWC_X_POST_MAX_CHARS`), `402` exhausted credits. A null `paper_id` without errors means every recent trending paper was already posted.
- **Dashboard evidence:** latest `paper_x_posts.posted_at` and posts in 24 h. Six runs a day normally post several papers, so a day without a post degrades the job; confirm with `SELECT posted_at, paper_id FROM paper_x_posts ORDER BY posted_at DESC LIMIT 10` before blaming X.

## `post_x_insight`

- **Effect:** Prints a JSON summary (`kind`, `subject_key`, `text`, `template`, `url`, `post_id`, `reply_id`, `tried`) and inserts one `x_insight_posts` row per post. A null `kind` means no tried kind had anything new (healthy). An `x_insight_rewrite_rejected` warning means Luna changed a number and the template was posted instead.
- **Independent proof:** Open `https://x.com/i/status/<post_id>`; check the numbers against the linked benchmark, method, or task page.
- **Correctness:** Same X errors as `post_trending_paper_to_x` (shared `X_POST_*` keys and credits). A SOTA post must name a paper published in the last 45 days that leads a leaderboard with at least 5 entries.
- **Dashboard evidence:** latest `x_insight_posts.posted_at` and posts in 72 h; a quiet run is healthy, so only three days without any insight degrade. Check `SELECT kind, max(posted_at), count(*) FROM x_insight_posts GROUP BY kind` for a kind that stopped posting.

## `scan_model_releases`

- **Effect:** Prints a JSON report of recent model releases from official lab feeds, unmapped Artificial Analysis models, and web news, and logs `model_release_radar_unindexed` / `model_release_radar_source_error` warnings. It upserts each unindexed feed or web release into `model_release_signals` and queues at most 6 `resolve-model-paper` jobs (trigger `model-release-radar`) per UTC day, logged as `model_release_radar_queued`. Exit 1 only when every source failed.
- **Independent proof:** Open one or two lab news pages and confirm the newest model announcement within 14 days appears in the report with the right indexed/unindexed status and `paper_id`. For a queued signal, check its job in `paper_curation_jobs` (`release_signal_id`) and, once resolved, the signal's `paper_id` page.
- **Correctness:** Recurring `source_error` for one lab means its feed or page layout changed. Signals stuck in `queued` mean scheduled curation is paused or saturated. A `rejected` signal with a news-page `source_url` refusal in its job's `validation_summary` means the curator could not find a first-party source; read its report before indexing by hand. A long-lived unindexed release that never becomes a signal is an Artificial Analysis slug (report-only) or a web hit seen only once.
- **Dashboard evidence:** report-only, so a successful systemd exit (the job exits 1 only when every source failed) is the output proof. Read the radar JSON from `journalctl -u pwc-cron-scan-model-releases.service --since '6 hours ago' -o cat | grep '^{'` for `sources_checked` versus `errors`.

## `export_enrichment_dashboard`

- **Effect:** Exports the private enrichment-dashboard artifact consumed by operators; it does not write catalog rows.
- **Independent proof:** Inspect the configured output object's mtime, size, schema/version, row count, and bounded hash. Recompute sampled aggregates from the database and compare them with the exported fields.
- **Limitation:** A successful launcher log without a fresh, parseable, internally consistent artifact is not durable-output proof. Do not expose private dashboard contents.
- **Dashboard evidence:** `/var/lib/paperswithcode/shared/enrichment-dashboard/snapshot.json` is stream-parsed (no size cap; it passed 18 MB on 2026-10-17) for `schema_version`, `generated_at`, and the `daily`/`papers`/`evaluations` list lengths.

## `sync_hf_organizations`

- **Effect:** Reconciles strict featured-organization metadata, logos, HF paper counts, papers, and paper-organization links.
- **Independent proof:** Load the deployed manifest and compare every member with current HF profile/papers: slug, count, logo hash/MIME, imported arXiv IDs, and junction coverage.
- **Trap:** The dashboard hard-codes a slug set and a fresh `last_hf_synced_at`; either can conceal partial reconciliation or manifest drift.

## `sync_hf_author_profiles`

- **Effect:** Applies HF paper authorship claims of the last 30 days: moves the claimed paper's `paper_authors` link to the account's own author row (created with `hf_username`, `hf_id`, `hf_avatar_url`, `hf_status`, `hf_is_pro` on first sight), sets `paper_authors.claimed`, and refreshes already-linked accounts.
- **Independent proof:** Sample recent HF papers with claimed authors (`/api/papers/<arxiv_id>`) and confirm the PwC paper links that account's author row with `claimed = true`; check `HF_AUTHOR_PROFILES_SUMMARY` for a sane `claimed`/`claims_seen` ratio.
- **Trap:** `recent_writes` counts any author update, and a quiet day with no new claims is healthy; `unmatched` claims (name spelled differently on arXiv) are expected and never linked.

## `link_openalex_organizations`

- **Effect:** Inserts missing `paper_organizations` rows with `source = 'openalex'` for arXiv papers published in the last 60 days, only for institutions in the reviewed map (`openalex_institutions.py`); never deletes links.
- **Independent proof:** Sample recent arXiv papers, query `https://api.openalex.org/works?filter=doi:10.48550/arxiv.<id>` directly, map author institution IDs through the reviewed map, and compare with the stored openalex links. Coverage of the newest two weeks is legitimately low because OpenAlex adds affiliations late.
- **Trap:** A run that ends with `OpenAlex returned 429` failed (budget spent); `PWC_OPENALEX_API_KEY` in `production-cron.env` gives 10,000 requests/day, the run needs about 30.

## `calculate_organization_trending_scores`

- **Effect:** Writes one daily raw history row per featured organization, updates its trailing-30-day mean/timestamp, and prunes old history.
- **Independent proof:** Require exactly one current-date row per manifest organization. Recompute raw signals and the 30-day arithmetic mean; check missing/duplicate days and retention bounds.

## `refresh_paper_embeddings`

- **Effect:** Upserts content-hashed vectors into the active embedding generation and records pipeline runs.
- **Independent proof:** Require exactly one active generation; anti-join all latest papers using an independently recomputed title+abstract hash. Check dimension, finite values, approximate unit norm, duplicates, orphans, and backlog trend.
- **Functional proof:** Query production semantic search with known titles and concepts; full row coverage can coexist with broken vector semantics.

## `preload_thumbnails`

- **Effect:** Generates/caches valid paper images and uploads thumbnail objects for several candidate lanes.
- **Independent proof:** Reconstruct each deployed candidate lane separately (visible, task/method, recent, external), derive expected filenames, and measure object coverage. Decode sampled images; verify dimensions/aspect, nonblank content, and current cohort identity.
- **Functional proof:** Sample `/api/thumbnails/{filename}` for status, MIME, decodability, and content. A global newest mtime does not prove lane coverage.
- **Trap:** All five lanes share the launcher's `preload_thumbnails` lock, so a lane whose slot arrives while another lane runs exits 0 with "preload_thumbnails is already running" and does no work. The launcher records each as a `lock_skipped` event, and the dashboard degrades the job for any skip in 24 h; name the skipped lane from `journalctl -u 'pwc-cron-preload-thumbnails-*' --since '24 hours ago' | grep 'already running'`.

## `mirror_thumbnails_to_disk`

- **Effect:** Incrementally mirrors the HF thumbnail bucket to the VPS cache; deletion is normally disabled.
- **Independent proof:** Compare bucket key manifest, sizes and bounded hashes/ETags with local files. Find bucket-present/local-missing or corrupt objects and verify newest bucket objects propagated.
- **Functional proof:** Sample public thumbnail serving from mirrored files. Extra local files are expected, not automatically unhealthy.

## `link_methods_by_references`

- **Effect:** Scans recent unprocessed papers, writes method links/reference evidence, and advances `methods_scanned_at`.
- **Independent proof:** Measure eligible null/stale backlog and weekly age distribution; validate evidence/link referential consistency and new evidence volume.
- **Correctness:** Compare sampled paper references with method source-paper identities and exclusions. A scan marker advanced after provider/parser failure is not proof.

## `backfill_method_keywords`

- **Effect:** Advances a versioned keyword-catalog run/cursor and writes method keyword evidence/links.
- **Independent proof:** Verify current catalog SHA, cursor monotonicity, processed-versus-eligible accounting, completion, and absence of stale/failed runs.
- **Correctness:** Run the deployed matcher read-only on stratified processed/unprocessed papers and anti-join expected matches against evidence/links/exclusions.

## `backfill_method_references`

- **Effect:** Advances per-method/month frontier ledgers and writes reference evidence/links.
- **Independent proof:** Verify frontier movement, cursor monotonicity, eligible accounting, stale/failed partitions, retries and 429s.
- **Correctness:** Compare bounded exact reference/source matches and exclusions; validate link/evidence consistency.

## `link_papers_by_task_keywords`

- **Effect:** Add-only auto task links. The junction has no reliable per-write timestamp.
- **Independent proof:** Load current task keywords, run the deployed matcher read-only over latest papers, and anti-join all expected `(paper_id, task_id)` pairs. Report gap count/sample and inspect a false-positive-sensitive sample.
- **Limitation:** Without a historical snapshot, temporal attribution is unverified; successful workflow logs alone do not prove writes.

## `review_submissions`

- **Effect:** When explicitly enabled, reviews claimed submissions and records a content-free terminal health record; in production it is intentionally disabled unless both autonomous-review flags are true.
- **Independent proof:** First verify both feature flags and timer state. Disabled plus inactive is `not_applicable`; disabled plus active is a configuration failure. If enabled, inspect claimed/terminal counts, oldest claim, dry-run/remote-launch flags, attempts, and health-record freshness without reading submission content.
- **Safety:** Never enable the timer, claim a submission, or invoke the reviewer merely to prove health. Validate a claimed run only through the supported scheduler and operator records.

## `monitor_chat_operational_alerts`

- **Effect:** A minutely systemd job reads content-free operational signals, writes private state and health JSON, and delivers primary/fallback alerts.
- **Independent proof:** Check timer/service cadence, health-record mtime/schema/status, journal cursor advancement, pending delivery states/attempts, and bounded history. Recompute provider/content-free journal health from source aggregates.
- **Limitation:** Alert delivery cannot be fully proven without authorized Slack/channel evidence. Do not inspect chat content.
- **Trap:** The health record reflects only the latest poll; on 2026-10-17 the unit had failed 557 times in a day while showing healthy. Read `execution_health.recent_runs` (launcher exits) or count `Failed with result` in the unit journal.

## `process_curation_thumbnails`

- **Effect:** A minutely systemd worker claims thumbnail requests, generates/uploads output, and records status/timestamps/dimensions/warnings/errors.
- **Independent proof:** Inspect queued, processing, stale-claim, failed, oldest-wait, attempts, and recent-completion distributions. For sampled succeeded rows, independently fetch/decode the URL or public endpoint and verify dimensions, nonblank content, and bucket/local presence.
- **Trap:** A succeeded database flag is insufficient when the object is absent or corrupt.
- **Dashboard evidence:** the queue is event-driven, so with nothing queued or processing a successful poll is healthy however old the last write; `failed` counts only failures finished in the last 24 hours.


## `create_eval_verification_issues`

- **Effect:** Checks eligible repositories and records GitHub verification outreach in a durable SQLite ledger.
- **Proof:** Open the ledger using SQLite URI `mode=ro`; compare last-run counts, pending repositories and rate-limit state with a bounded GitHub issue sample. Match cited evaluations and eligible repository coverage; exit zero is insufficient proof of outreach completeness.
- **Safety:** Do not invoke the issue creator or send a GitHub message as an audit probe.

## `run_chat_synthetic_probe`

- **Effect:** A timer checks the synthetic probe gate and writes a content-free health record; actual probes consume production capacity.
- **Proof:** Compare health record status/reason/mtime with the `chat_reliability` operator state. Operator-disabled probes are not applicable, while their gate timer should still terminate successfully.
- **Safety:** Do not launch a probe solely to verify health.

## `autonomous_cron_audit` and `autonomous_cron_health`

- **Effect:** Daily audit and frequent strict snapshot jobs record autonomous CRON run/action/intent/budget/lease state.
- **Proof:** Read operator state and actual `autonomous-cron-{audit,health}.timer` units first. Disabled operators with inactive timers are not applicable. When enabled, verify cadence, terminal runs, action/intent correspondence, reservations and unreleased leases.
- **Trap:** These units do not use the generated `pwc-cron-` prefix; inspect them explicitly.

## `sync_open_tts`

- **Contract:** English and all-language Open TTS datasets have separate managed rows and WER/RTFx metrics.
- **Proof:** Compare each dataset independently with the official source; recompute the English macro-average across Seed-TTS and CV3-Eval, verify model identity, units, stale-row removal and rank direction. Freshness in one lane does not prove the other.

## `send_research_digests`

Hourly timer; new digests cover the week ending Monday at 08:00 UTC. The other
runs are no-ops outside the 23-hour retry window. Delivery is intentionally
disabled until all Resend launch gates are configured. Do not enable gates or
send test mail as a health probe. Inspect aggregate `research_digests` counts
by window/status, never recipient addresses or payloads. `uncertain` requires
provider reconciliation before any manual resend; provider idempotency lasts
24 hours. A disabled/no-work outcome is healthy during staged rollout.

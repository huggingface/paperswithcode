# Independent data-plane probes

This reference describes the current production contracts. Discover job IDs dynamically from the active release, then use the matching section. If the registry contains an ID without a section, inspect its deployed workflow, script, services, and persistence models; mark probe coverage drift rather than skipping it.

For each job, retain bounded evidence: cohort size, missing/stale/error counts, oldest or percentile age, a deterministic recomputation or upstream sample, and one user-visible read where applicable. Dashboard freshness queries are useful baselines but are not independent proof.

## Shared leaderboard sync procedure

For every managed leaderboard sync, fetch the current upstream source read-only and independently normalize its row keys. Compare the complete bounded set when feasible, otherwise a stratified sample plus set/count aggregates. Verify model/release identity, metric values and units, evaluation date/harness/source, expected dataset, managed methodology, row ownership, stale-row deletion, preservation of unrelated manual rows, rank direction, ties, and the public benchmark API. A recent `evaluations.updated_at` only proves rows were touched.

## `paper_markdown_backfill`

- **Effect:** Creates/copies paper Markdown objects and `_jobs/status/*.json` plus coverage/progress records in the paper-Markdown Hugging Face bucket; may launch OCR jobs.
- **Independent proof:** Anti-join all latest arXiv papers—and recent 14-day papers separately—against expected object keys. Classify missing, invalid, empty, oversized, failed, interrupted, and unresolved-volume-mount states. Inspect coverage-history movement and orphan keys.
- **Correctness:** Decode a stratified sample and verify nontrivial text, title/arXiv identity, version, and absence of obvious OCR/error payloads. Key existence alone is insufficient.

## `update_hot_github_trending`

- **Effect:** Refreshes 0–30-day official repositories, star history, repository EMA trending, and linked recent paper trending components/scores.
- **Independent proof:** Reconstruct eligible hot repo groups; measure queue coverage, oldest wait, one-snapshot starvation, and linked stale paper scores. Compare sampled GitHub `stargazers_count` to repository values and latest star-history rows.
- **Correctness:** Recompute repository EMA and paper composite scores from durable inputs; compare exact or tolerance-bounded results and public trending ordering.

## `update_github_stars`

- **Effect:** Refreshes `repositories.num_stars`, `num_stars_updated_at`, and `repository_star_history` for 31–180-day hourly and older weekly queues.
- **Independent proof:** Partition eligibility by queue, inspect age distribution and oldest wait, and ensure duplicate owner/name records agree. Compare a stratified GitHub API sample with stored stars and latest snapshots; inspect implausible deltas.
- **Trap:** Terminal 404/451 handling may advance a checked timestamp without changing stars. Count these separately from successful refreshes.

## `update_citations`

- **Effect:** Updates paper citation count, Semantic Scholar ID, and `citation_updated_at` across cadence buckets.
- **Independent proof:** Reconstruct eligible/backlog buckets and their age distribution. Compare a bounded stratified sample directly with Semantic Scholar using stable paper identity; verify the stored ID and count.
- **Correctness:** Flag suspicious mass zeroing/decreases and timestamps advanced after not-found/error outcomes. A fresh maximum timestamp is weak evidence.

## `extract_urls`

- **Effect:** Manual/paused pipeline marks `urls_extracted` and writes official repositories/project pages plus junctions.
- **Independent proof:** Report schedule as `not_applicable`. If auditing a claimed dispatch, measure unresolved backlog and false-complete papers with no official resource; sample linked URLs for HTTP reachability, canonical GitHub identity, and officialness.
- **Safety:** Do not invoke select/discover/persist to test health.

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

## `sync_open_tts`

- **Contract:** `open-tts-leaderboard` is the English macro-average and `open-tts-leaderboard-all-languages` is the macro-average across every available language, both over Seed-TTS and CV3-Eval. Managed rows come from the official Open TTS HF Space, rank by lower-is-better WER, and may also carry RTFx.
- **Independent proof:** Fetch both current Gradio tables read-only with the exact deployed language/dataset filters. Compare the complete validated model set, WER, RTFx, upstream rank, HF model identity, paper mapping, open status, managed methodology, and stale-row deletion independently for each dataset.
- **Correctness:** Require the expected language choices and plausible row-count bounds before comparing. Verify that English and all-language aggregates were not swapped or copied, WER ranks are ascending with ties handled correctly, unrelated manual rows survive, and both public benchmark APIs match the recomputed tables.

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

## `sync_programbench`

- **Contract:** `programbench`; Resolved, Almost Resolved, and Average Test Pass Rate; mini-SWE-agent; typically 15–60 rows.
- **Proof:** Compare the current embedded upstream results and run URLs; verify units, owned row set, and rank semantics.

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

## `create_eval_verification_issues`

- **Effect:** Reconciles recent evaluation-outreach candidates into a protected SQLite ledger and creates at most ten GitHub verification issues per run; aliases, pending posts, rate-limit cooldown, and the last-run summary make retries idempotent.
- **Independent proof:** Read the ledger through the script's `--status` mode, then independently recompute the bounded recent candidate cohort from the catalog. Compare repository identities with the complete paginated GitHub issue set, including open and closed matches, and verify every pending checkpoint resolves to exactly one issue or a recorded review/cooldown state.
- **Correctness:** Inspect `last_run` counts/events, oldest pending repository, duplicate issue identities, uncertain-post `needs_review`, and rate-limit expiry. A fresh log or empty pending list is insufficient if eligible repositories were omitted or GitHub pagination stopped early. Never use `--execute` as a health probe.

## `enqueue_hf_daily_paper_curation`

- **Effect:** Reconciles the rolling HF cohort into versioned workflows and two-stage jobs; downstream jobs mutate enrichments/evaluations and may request thumbnails.
- **Independent proof:** Compare unique rolling cohort to workflows under active policy; inspect missing/duplicate/deferred reasons, queue age, scheduler state, canary, attempts, and terminal outcomes.
- **Correctness:** For completed/satisfied workflows, verify expected paper mutations and proposal/mutation result—not merely workflow creation. Treat failed/partial/deferred counts as findings even if the generic dashboard evaluator ignores them.

## `enqueue_hf_trending_model_curation`

- **Effect:** Discovers trending HF model candidates, advances their resolver states, and may enqueue bounded paper-curation workflows.
- **Independent proof:** Compare a bounded current Hub trending cohort with candidate identities and `last_seen_at`; inspect missing/duplicate candidates, active/resolved/failed states, oldest wait, attempts, and downstream workflow linkage.
- **Correctness:** Sample resolved candidates and verify canonical paper identity plus resulting enrichment. Fresh candidate timestamps alone do not prove resolution or application.

## `export_enrichment_dashboard`

- **Effect:** Exports the private enrichment-dashboard artifact consumed by operators; it does not write catalog rows.
- **Independent proof:** Inspect the configured output object's mtime, size, schema/version, row count, and bounded hash. Recompute sampled aggregates from the database and compare them with the exported fields.
- **Limitation:** A successful launcher log without a fresh, parseable, internally consistent artifact is not durable-output proof. Do not expose private dashboard contents.

## `sync_hf_organizations`

- **Effect:** Reconciles strict featured-organization metadata, logos, HF paper counts, papers, and paper-organization links.
- **Independent proof:** Load the deployed manifest and compare every member with current HF profile/papers: slug, count, logo hash/MIME, imported arXiv IDs, and junction coverage.
- **Trap:** The dashboard hard-codes a slug set and a fresh `last_hf_synced_at`; either can conceal partial reconciliation or manifest drift.

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

## `run_chat_synthetic_probe`

- **Effect:** Runs a production-only, content-free synthetic chat when the four-hour gate or a release/critical-alert trigger is due, records transition events in `chat-synthetic-probe-state.json`, writes `chat-synthetic-probe-health.json`, and retries pending primary/fallback alert delivery.
- **Independent proof:** Check the systemd minute cadence separately from the internal due gate. Validate health/state JSON schema and mtimes, `last_synthetic_probe_at`, active-probe age, release/runtime revision triggers, recent transition events, pending delivery states/attempts, and the absence of overlapping active probes. Corroborate the latest due run with content-free production reliability telemetry only.
- **Correctness:** Classify intentional `dormant` or mutation `paused` states separately from healthy execution. A minute timer success with no due probe is not end-to-end proof; an overdue four-hour probe, stale `synthetic_active`, undelivered event, release-trigger miss, or synthetic failure is a finding. Do not inspect user chats or invoke a synthetic run merely to test health.

## `autonomous_cron_health`

- **Effect:** Every 15 minutes, builds a strict multi-plane dashboard snapshot, selects at most one unhealthy job, and records a fenced retry/source-repair/no-op outcome in `autonomous-cron-operator-health.json` plus autonomous run/action ledgers and alert receipts.
- **Independent proof:** Verify timer/service cadence and health-file schema/mode, then independently rebuild the strict snapshot from the current registry, scheduler state, logs, locks, freshness providers, and output evaluators. Match the selected job, before/after finding digests, reason code, run ID, policy decision, action ledger, alert receipt, and any published SHA or rollback record.
- **Safety:** Read-only comparison is the probe. Do not trigger the operator or retry a job to demonstrate health. Treat `monitoring_only` as an operator-policy outcome, not proof that the selected CRON recovered; verify the underlying finding again.

## `autonomous_cron_audit`

- **Effect:** Runs the daily-mode four-plane audit at 02:20 UTC, handles at most one selected finding under the same fenced policy, builds the daily digest, and records digest-delivery evidence. It shares the operator health filename with strict mode, so a later strict run may replace the daily file.
- **Independent proof:** Prove the daily timer occurrence from systemd/journal and the autonomous run/action and alert-receipt ledgers rather than relying only on the shared JSON file. Rebuild the daily snapshot, compare all findings and selected-job digests, and verify exactly one current-day digest payload/receipt with bounded aggregate counts.
- **Correctness:** Distinguish audit completeness from successful remediation and notification delivery. Flag a missing daily run/digest, partial plane inventory, stale or duplicate digest, unexplained finding suppression, unauthorized action, or mismatch between the daily snapshot, durable ledgers, and delivery receipt.

## `process_curation_thumbnails`

- **Effect:** A minutely systemd worker claims thumbnail requests, generates/uploads output, and records status/timestamps/dimensions/warnings/errors.
- **Independent proof:** Inspect queued, processing, stale-claim, failed, oldest-wait, attempts, and recent-completion distributions. For sampled succeeded rows, independently fetch/decode the URL or public endpoint and verify dimensions, nonblank content, and bucket/local presence.
- **Trap:** A succeeded database flag is insufficient when the object is absent or corrupt.

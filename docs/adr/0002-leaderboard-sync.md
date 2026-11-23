# ADR 0002: Third-party leaderboard syncs

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## 3D Arena sync treats a validated upstream response as authoritative

A successful, validated 3D Arena response is authoritative for which models exist: managed rows whose model disappeared are deleted, while rows for models still present but temporarily unresolved are protected. Duplicate leftovers for the same model with a stale source URL are deleted so the canonical Space URL row is the only managed copy.

Code: `backend/services/three_d_arena_sync_service.py::ThreeDArenaSyncService.sync`

## 3D Arena unknown models use the product name as their lab

The 3D Arena Space publishes no organization for its models. Unknown models are passed to the shared matcher with the product name standing in for the lab, because using "3D Arena" would make the leaderboard Space itself look like a first-party source for the release radar.

Code: `backend/services/three_d_arena_sync_service.py::ThreeDArenaSyncService.sync`

## A new Intelligence Index version retires unlisted older rows

Each Intelligence Index version rescales every score. When a managed row's model is no longer listed and the row's methodology names an older index version, the sync deletes it because it no longer compares with current rows. Rows for unlisted models on the current version are kept.

Code: `backend/services/artificial_analysis_sync_service.py::ArtificialAnalysisSyncService.sync`

## ARC Prize sync imports only single-model entry types

The ARC Prize leaderboard tags entries with a model type. Only 'CoT' and 'Base LLM' name a single model; 'Refinement', 'Custom' and 'CoT + Synthesis' are systems built on top of a model, and human baselines have no type. The sync imports only the single-model types so leaderboard rows map to one model release.

Code: `backend/services/arc_prize_sync_service.py::MODEL_TYPES`

## Adoption falls back to paper and model name, ignoring harness

Hand-imported evaluation rows often record the harness as 'Not reported', so they do not match the sync's (paper, model, harness) identity. When no managed row matches, the sync falls back to an unmanaged row with the same paper and model name and adopts it, instead of creating a duplicate.

Code: `backend/services/live_leaderboard_sync.py::LiveLeaderboardSyncService.sync`

## Artificial Analysis Decision Index sync is pinned to v2.1

Artificial Analysis publishes a versioned headline Decision Index, and each version reweights its components so scores are not comparable across versions. The sync accepts only v2.1; a new upstream version needs human review before its scores replace the existing rows.

Code: `backend/services/artificial_analysis_decision_sync_service.py::INDEX_VERSION`

## Artificial Analysis TTS publishes only reviewed paper identities

The TTS arena sync publishes a model only when its mapping to a canonical paper has been reviewed against the Artificial Analysis catalog and added to MODEL_PAPER_IDENTITIES. Newly listed upstream models stay absent until a human identifies their paper, avoiding wrong attributions.

Code: `backend/services/artificial_analysis_tts_sync_service.py::MODEL_PAPER_IDENTITIES`

## Artificial Analysis free API quota is shared by the sync and the release radar

The free Artificial Analysis Data API key allows 100 requests per day, and a full fetch costs one request per 200-model page. The two-hourly leaderboard sync and the three-hourly model release radar draw on that same budget. Raising either schedule or adding another consumer must account for the shared quota, which the sync reports from response headers.

Code: `backend/services/artificial_analysis_sync_service.py::API_ENDPOINT`

## Blueprint-Bench 2 skips starred baseline and below-random rows

On the Blueprint-Bench 2 board, a name ending in `*` ("Human*") is a 12-apartment human baseline and a score ending in `**` marks results at or below the random baseline, which the board does not rank. The parser skips both so only ranked model rows are synced.

Code: `backend/services/carbon_board_syncs.py::parse_blueprint_bench_2`

## Claude Mythos Preview is a separate model identity

Claude Mythos Preview was released only to Project Glasswing partners and is a model of its own, not a preview checkpoint of Claude Mythos 5. It keeps its own identity and system card source; folding it into Claude Mythos 5 would merge scores of different models.

Code: `backend/services/carbon_board_identities.py::IDENTITIES`

## CoArena accepts ranked, provisional and stable statuses

CoArena publishes a stable rating status for long-standing top models in addition to ranked and provisional. All three are accepted as valid; treating stable as invalid makes the parser reject the payload and aborts the hourly sync.

Code: `backend/services/coarena_sync_service.py::VALID_RATING_STATUSES`

## CoArena company is optional display metadata

CoArena may omit company for a rated model. Company is used only for display and release-radar attribution, so a missing value is accepted, while stable ids, ratings and paper mappings remain mandatory and invalid ones abort the parse.

Code: `backend/services/coarena_sync_service.py::parse_coarena_leaderboard`

## CoArena maps exact upstream ids to reviewed paper identities

Exact CoArena model ids are the trust boundary between a product label and a paper. A model is attached to a paper only after its release identity has been reviewed and added to MODEL_PAPER_IDENTITIES; new upstream models stay unmatched rather than being guessed from names.

Code: `backend/services/coarena_sync_service.py::MODEL_PAPER_IDENTITIES`

## CoArena rows are keyed by stable id after upstream dropped model

On 2026-11-13 CoArena removed the provider model field from its leaderboard rows. The parser now treats the stable id as the paper-identity key and name only as the display label; both are required and must be unique.

Code: `backend/services/coarena_sync_service.py::parse_coarena_leaderboard`

## Curated exact names are the trust boundary for synced model identities

The Artificial Analysis sync links model variants to papers only through a reviewed map of exact slugs to canonical technical reports or official release pages. Upstream additions stay unmatched until their source has been reviewed, so scores are never attributed to a guessed paper.

External leaderboard syncs attach rows to introducing papers only through a reviewed map of exact board row names. Names outside the map are matched automatically only when the catalog names them unambiguously, and otherwise go to the model release radar for review. Fuzzy matching beyond this would risk attributing scores to the wrong paper.

The SLE sync attaches rows to introducing papers only through a reviewed map of exact model names. Other names are matched automatically only when the catalog names them unambiguously, and otherwise go to the model release radar.

Code: `backend/services/artificial_analysis_sync_service.py::MODEL_PAPER_IDENTITIES`, `backend/services/rsi_exam_sync_service.py::MODEL_IDENTITIES`, `backend/services/sle_sync_service.py::MODEL_IDENTITIES`

## CyberGym DeepSeek rows map to dated V4 checkpoints

Upstream CyberGym DeepSeek rows link the 0813 and 0731 checkpoints described in the DeepSeek-V4 report. The catalog names these models by checkpoint and reasoning mode (for example 'DeepSeek-V4-Pro-0813 (Max)') rather than the bare family name, so scores from different checkpoints are not merged.

Code: `backend/services/carbon_board_identities.py::IDENTITIES`

## CyberGym sync mirrors the site's default model-focused view

The CyberGym site's default "Model-focused" view leaves out runs against the cleaned vulnerable image (`dynamic`) and runs with a test-time knowledge base (`test-time mem.`). The sync excludes those feature labels, plus multi-trial and hidden rows, so the PwC board matches the ranking CyberGym itself presents.

Code: `backend/services/carbon_board_syncs.py::CYBERGYM_EXCLUDED_FEATURES`

## DeepSWE models map to papers via a reviewed table, then unambiguous catalog matches

Upstream DeepSWE model slugs are mapped to papers through MODEL_PAPER_IDENTITIES, a reviewed table of release identities. Slugs not in it are attached only when the catalog names them unambiguously as a model release or alias; everything else is reported as an unmatched model and handed to the release radar instead of guessed.

Code: `backend/services/deepswe_sync_service.py::MODEL_PAPER_IDENTITIES`

## DeepSWE sync adopts hand-imported legacy rows

Some DeepSWE v1.1 rows were imported by hand before the managed sync existed. LEGACY_MODEL_NAMES maps upstream slugs to those legacy model names so the first sync adopts the rows instead of creating duplicate leaderboard entries. Removing an entry before adoption would duplicate that model.

Code: `backend/services/deepswe_sync_service.py::LEGACY_MODEL_NAMES`

## DeepSWE sync deletes only managed rows absent from a validated response

A validated upstream response is authoritative for which models exist. The sync deletes managed rows whose model key no longer appears upstream, but keeps rows for models still present even if they cannot currently be resolved to a paper, so a transient match failure never drops a live entry.

Code: `backend/services/deepswe_sync_service.py::DeepSweSyncService.sync`

## Drex Max maps to its technical report

The Drex model-card page was merged into the Drex technical report, so the JevBench identity for Drex Max points at the arXiv report rather than a separate model-card source.

Code: `backend/services/jevbench_sync_service.py`

## Drex Max v1.1 is closed-weight while Drex v2.0 is open

Both Drex entries on the Decision Index cite the same report (arXiv 2611.07854), but Drex Max v1.1 is served by API only while v2.0 has public weights. Their paper identities therefore differ in is_open and must not be unified onto one shared identity.

Code: `backend/services/artificial_analysis_decision_sync_service.py::MODEL_PAPER_IDENTITIES`

## Evaluation edits check duplicates only on identity changes

update_evaluation lets existing rows be edited freely, even if legacy duplicates already exist. The duplicate-entry guard runs only when the edit changes the leaderboard (task or dataset) or model identity, so an edit cannot move a row onto another row's entry, while routine metric or metadata edits on historical duplicates are not blocked.

Code: `backend/services/evaluation_service.py::EvaluationService.update_evaluation`

## Exact upstream labels are the trust boundary for live leaderboard identities

Live leaderboard syncs (for example ExtractBench and JevBench) link upstream rows to papers only through exact, reviewed upstream labels in a hand-maintained identity map. Unreviewed labels are not fuzzily attached: ExtractBench leaves them unpublished and reports them, while JevBench matches only unambiguous catalog names and otherwise hands them to the release radar. Coding-agent rows such as Claude Code or Codex resolve to their underlying model. This prevents a similarly named row from being credited to the wrong paper.

Code: `backend/services/extractbench_sync_service.py`, `backend/services/jevbench_sync_service.py`

## ExploitGym sync keeps only full-set runs under the 6-hour budget

ExploitGym publishes runs under several protocols. Only full-set runs under the board's 6-hour budget ("6h timeout" and "rescaled 6h timeout") are comparable, so the sync filters to those protocols.

Code: `backend/services/carbon_board_syncs.py::EXPLOITGYM_PROTOCOLS`

## ExtractBench OSS category marks open-weight models

ExtractBench lists open-weight models under the 'OSS' category. The sync treats a row as open when its category is 'OSS' or when the matched paper is already marked open, so open-weight status is not lost when the catalog paper lacks it.

Code: `backend/services/extractbench_sync_service.py::ExtractBenchSyncService.sync`

## ExtractBench auto-matches only single-model categories

Only ExtractBench rows in the 'Commercial VLM' and 'OSS' categories are single models that may be matched automatically to catalog papers. Other categories are extraction products, coding-agent harnesses and LlamaExtract tiers; they are published only through a reviewed provider identity or listed as reviewed exclusions.

Code: `backend/services/extractbench_sync_service.py`

## ExtractBench exclusions are reviewed, not unreviewed

Extraction products without an introducing paper or official model release page, and third-party extraction harnesses wrapped around a model (such as KYNEX or Pi variants), are listed in EXCLUDED_PROVIDERS. They are deliberate reviewed exclusions, so the job does not report them as unreviewed rows needing attention, and they are never published as model releases.

Code: `backend/services/extractbench_sync_service.py`

## ExtractBench infers the lab from the provider label

The ExtractBench CSV has no lab column. _leaderboard_model takes the lab of a known model family in the label (for example 'Qwen3.8 27B'), otherwise the vendor the label starts with (for example 'OpenAI GPT-6'), via vendor_label_model.

Code: `backend/services/extractbench_sync_service.py::_leaderboard_model`

## ExtractBench syncs from the upstream leaderboard CSV

The ExtractBench README leaderboard and its grounding tables are both rendered from leaderboard.csv in the run-llama/ExtractBench repository. The sync reads that CSV directly rather than scraping README tables, so it gets every column from the single upstream source of truth.

Code: `backend/services/extractbench_sync_service.py`

## FrontierCS 2 is scraped from its JavaScript data bundle

The FrontierCS leaderboard page renders client-side from constants in assets/js/fcs2-data.js, so the HTML has no scores. The sync fetches that bundle and decodes its literals with js_literal instead of parsing the page.

Code: `backend/services/frontiercs_2_sync_service.py::FRONTIERCS_2_DATA_URL`

## Live leaderboard syncs delete managed rows that left the board

A validated upstream board is authoritative for which entries it lists. The shared live leaderboard engine deletes a managed row once its upstream entry label, recorded in the methodology head, is no longer listed (excluded names still count as listed). A row with reviewer notes beneath the head is kept and reported, because the notes may carry provenance worth a human look. A row that also carries another board's metric on a shared benchmark (Physics-IQ's two tracks) loses only this board's metric. Boards that stop charting older models without restating their scores (the Artificial Analysis CritPt, CritPt v2 and Terminal-Bench-Science pages) set retire_missing=False and keep those rows, matching the main Artificial Analysis sync's policy for unlisted models on the current index version.

Code: `backend/services/live_leaderboard_sync.py::LiveLeaderboardSyncService.sync`, `backend/services/carbon_board_syncs.py::BOARD_SYNCS`

## FrontierCS sync deletes managed rows that left the board

FCI is refitted on every FrontierCS update, so a row the board no longer lists keeps a score from an older fit that no longer compares with current rows. A validated response is therefore authoritative: the sync deletes managed rows whose upstream model name and harness, recorded in the methodology, are no longer listed. Rows for entries still listed but unresolved, and rows not written by the sync, are kept.

Code: `backend/services/frontiercs_2_sync_service.py::FrontierCS2SyncService.sync`

## FrontierCS effort variants collapse to one best row per model

Different reasoning-effort settings of one model map to the same catalog model name. The FrontierCS board keeps only the best row per (paper, model name, harness), consistent with the rule that a leaderboard shows each model's best eval per paper.

Code: `backend/services/frontiercs_2_sync_service.py::FrontierCS2SyncService.sync`

## FrontierCS entries link to papers only through reviewed exact model names

Exact FrontierCS model names are the trust boundary between a leaderboard entry and its introducing paper. MODEL_IDENTITIES pins reviewed names to catalog model names and papers consistent with the Vals AI sync; other names are matched automatically only when the catalog names them unambiguously, and otherwise are reported to the release radar.

Code: `backend/services/frontiercs_2_sync_service.py::MODEL_IDENTITIES`

## FrontierCS pass rates are validated against pass counts within half a tenth

The site publishes pass rates as one-decimal percentages alongside pass and run counts. The parser accepts a published rate only if it is within 0.05 percentage points of passed/runs, which tolerates either rounding direction of a half tenth while rejecting inconsistent data.

Code: `backend/services/frontiercs_2_sync_service.py::parse_frontiercs_2`

## FrontierCode model labs are inferred from unique legend colors

The FrontierCode leaderboard has no lab field; its legend colors each model by lab. A model's lab is assigned only when exactly one lab uses that color, and left unknown when colors are shared, to avoid misattributing models.

Code: `backend/services/frontiercode_sync_service.py::parse_frontiercode_leaderboard`

## FrontierCode sync pins reviewed papers and auto-matches the rest

MODEL_PAPER_IDENTITIES lists exact, reviewed introducing papers or release pages for every model on FrontierCode when it was last reviewed, and the parser fails if a reviewed model disappears. Models not in the map are matched automatically only when the catalog names them unambiguously; otherwise they are handed to the model release radar.

Code: `backend/services/frontiercode_sync_service.py`

## GLM-4.6V Flash maps to the GLM-4.5V / GLM-4.1V-Thinking report

GLM-4.6V has no report of its own; its model card cites the GLM-4.5V / GLM-4.1V-Thinking report (arXiv 2507.01006). The ExtractBench identity for GLM-4.6V Flash therefore points at that paper, which would otherwise look like a version mismatch.

Code: `backend/services/extractbench_sync_service.py`

## Gradio Space calls use keyword arguments

On 2026-10-22 the Open ASR Space added a leading version_id input, which misaligned positional client.predict arguments. The sync passes every input by keyword so new Space inputs do not silently shift values.

Code: `backend/services/open_asr_sync_service.py::fetch_open_asr_leaderboard`

## Intelligence Index sanity floor allows partial re-scoring

The sync refuses Intelligence Index responses with fewer than 50 scored models. The floor is set this low because Index v5 (2026-10-27) re-scored only 77 models at launch; a higher floor would reject legitimate responses after a version bump.

Code: `backend/services/artificial_analysis_sync_service.py::INTELLIGENCE_INDEX`

## JevBench attributes vendors by source host, then by name prefix

JevBench names often end in the vendor, which the published row name drops (for example 'Drex Max (Nace AI)'). The sync therefore takes the vendor from the host of the system's source URL, and only for systems whose source is a third-party host (OpenRouter, a Hugging Face repo) or missing, from a reviewed row-name prefix.

Code: `backend/services/jevbench_sync_service.py`

## JevBench keeps each general LLM's best reasoning setting

JevBench measures general LLMs as decision models through their chat APIs and lists one row per reasoning setting. All settings map to the same model identity, and only each model's best-scoring setting is kept on the PwC board, so one model does not occupy several rows.

Code: `backend/services/jevbench_sync_service.py`

## JevBench sync pins the scoring method version

Each new JevBench scoring method restates every score on a different scale. The sync pins METHOD (currently v1.7) so a method change upstream does not silently move managed rows; a reviewer decides whether the managed leaderboard switches to the new method.

Code: `backend/services/jevbench_sync_service.py`

## Leaderboard model-cell badges are display markers, not identity

Since 2026-11-14 the Open TTS leaderboard appends display badges such as 'NEW' after the model link. The model-link pattern allows trailing span and sup markers so they neither break parsing nor change the model identity.

Code: `backend/services/open_tts_sync_service.py::_MODEL_LINK_RE`

## Leaderboard source dates use the Space createdAt when the citation gives only a year

The Open TTS Leaderboard citation states only the year 2026. Rather than inventing a January 1 publication date, the source paper date is the Hugging Face Space's public createdAt date (2026-09-07). Apply the same rule for other year-only leaderboard sources.

Code: `backend/database/datasets_setup/add_open_tts_leaderboard.py::SOURCE_DATE`

## Live leaderboard scores supersede curated rows for the same paper and model

A curated evaluation naming the same upstream model on the same paper, for example a paper-reported score from an older board version, is replaced by the live Open ASR score rather than shown beside it, so the leaderboard never lists a model twice.

Code: `backend/services/open_asr_sync_service.py::OpenAsrSyncService.sync`

## Live leaderboard syncs use exact reviewed model-name manifests

For live leaderboard syncs such as SWE-Marathon and 3D Arena, an exact, reviewed mapping from upstream model names to introducing papers is the trust boundary between a leaderboard row and a PwC paper. Names outside the manifest are matched automatically only when the catalog names them unambiguously, and otherwise are reported to the release radar; product names without a defensible paper stay unmatched.

The 3D Arena sync maps upstream model labels to arXiv papers through a deliberately exact manifest, which is the trust boundary between an upstream label and a PwC paper. Product names without a defensible paper are left unmatched rather than guessed.

Code: `backend/services/swe_marathon_sync_service.py`, `backend/services/three_d_arena_sync_service.py`

## Live leaderboard values keep the board's published precision

LeaderboardEntry.value accepts a Decimal so a sync preserves the precision the upstream board publishes (65.40 rather than 65.4). Converting to float at parse time would drop trailing zeros that the board treats as significant.

Code: `backend/services/live_leaderboard_sync.py::LeaderboardEntry`

## Live leaderboards keep each catalog model's best row

Several upstream rows, such as different reasoning settings or providers, can resolve to one catalog model. Live leaderboard syncs keep only that model's best-scoring row per paper, model name and harness, so one model does not occupy several leaderboard entries.

Code: `backend/services/live_leaderboard_sync.py::LiveLeaderboardSyncService.sync`

## Live sync collapse floor counts distinct models

Live leaderboard syncs refuse to replace a managed board when the reviewed subset falls below min_selected. Because several upstream labels (settings, prompt variants) can name one catalog model, the floor counts distinct (paper, model name) pairs the board would publish, not raw labels, so variants cannot mask a collapse.

Code: `backend/services/live_leaderboard_sync.py::LiveLeaderboardSyncService.sync`

## LlamaExtract tiers map to the ExtractBench paper as closed systems

The ExtractBench paper is LlamaIndex's own report on its LlamaExtract tiers, so every LlamaExtract row is linked to that arXiv paper and marked not open. There is no separate model release for these commercial product tiers.

Code: `backend/services/extractbench_sync_service.py`

## LlamaParse rows attach to the ParseBench reports

LlamaParse has no standalone paper; the ParseBench and ParseBench-2 reports are LlamaIndex's own write-ups of its LlamaParse pipelines. LlamaParse leaderboard rows are attached to those reports, marked closed (is_open False).

Code: `backend/services/parsebench_sync_service.py::_LLAMAPARSE`, `backend/services/parsebench_sync_service.py::PARSEBENCH_2_MODELS`

## MMEB-v3 syncs the Overall column, not Overall-V3

The MMEB Space ranks its v3 board by the "Overall" column, which averages all V3 datasets. The similarly named "Overall-V3" column averages only datasets new in V3, a subset, so it is not the board score. The v3 sync lane reads "Overall"; v2 reads "Overall-V2".

Code: `backend/services/mmeb_sync_service.py::LANES`

## MMTEB model-to-paper overrides pick the model's own report

Some MMTEB model cards cite both the model's own report and an earlier report that is linked to the same HF repository (for example KaLM-Embedding-V2 vs V1, E5-Mistral vs original E5). A curated map names the model's own arXiv report, and is applied only when the upstream citation list includes that id, so the override cannot attach an uncited paper.

Code: `backend/services/mmteb_sync_service.py::MODEL_ARXIV_OVERRIDES`

## Managed rows missing from the Decision Index page are retired

The Artificial Analysis Decision Index page lists every scored contestant, so a sync-owned row whose source URL is no longer selected was withdrawn upstream or collapsed into a better effort setting. The sync deletes such rows, but only those carrying its managed methodology prefix.

Code: `backend/services/artificial_analysis_decision_sync_service.py::DecisionIndexSyncService.sync`

## Managed-head pattern accepts legacy 'reported at' wording

Managed live-leaderboard rows are recognized by a methodology head pattern. Physics-IQ Verified rows written before 2026-11-09 end their head with 'reported at' instead of 'listed at', so the pattern accepts both. Tightening it to 'listed at' would make those stored rows look unmanaged.

Code: `backend/services/live_leaderboard_sync.py::LiveLeaderboard.managed_head`

## Matched leaderboard rows keep the board's model spelling

Matched models are stored under the leaderboard's own spelling rather than the release's canonical name. A model first matched by paper title and later by its model release therefore keeps the same row instead of creating a duplicate.

Code: `backend/services/leaderboard_model_matching_service.py::LeaderboardModelMatcher.match`

## Mistral Large 4 OSS maps to the open-weight checkpoint, not the API preview

Carbon boards list a 'Mistral Large 4 OSS' row. It is the open-weight checkpoint released after roughly three more weeks of RL beyond the API preview, so it is linked to the open-weight technical report and marked open. Merging it with the API preview would attribute different scores to one model.

Code: `backend/services/carbon_board_identities.py::IDENTITIES`

## Mistral Large 4 is keyed under both Vals labels

Vals switches between labelling the model "Mistral Large 4" and "Mistral Large 4 Preview". Both labels map to the same identity so the row stays linked to the same paper regardless of which label the upstream page shows; removing either key makes that row drop out of the sync when upstream flips.

Code: `backend/services/vals_finance_agent_sync_service.py`

## Model-name identity ignores case, spacing and separators but not symbols

Leaderboard display entries are deduplicated by a normalized model name: case, whitespace and separators such as hyphens, underscores, dots, commas, colons, parentheses, brackets and slashes never distinguish two models (I-DLM-32B equals I-DLM (32B)), while symbols such as + or * do (DAT and DAT+ are different models).

Code: `backend/services/evaluation_entry_identity.py::_MODEL_NAME_SEPARATORS`

## Muse Spark maps to the original API model

The May 2026 safety report that sources the 'Muse Spark' row evaluates the original API model, not the October open-weight Muse Spark Open release. The identity therefore points at the safety report and is not marked open; mapping it to the open release would misattribute scores and openness.

Code: `backend/services/carbon_board_identities.py::IDENTITIES`

## Only CWE-bench v2 is synced; v1 is a frozen archive

Collinear AI replaced CWE-bench v1 with v2 on 2026-11-02 and moved v1 to a frozen archive at /v1. The live sync targets v2 only; the cwe-bench-v1 board is no longer synced and should not be re-added to the registry.

Code: `backend/services/carbon_board_syncs.py::CWE_LIST_NAME`

## Only ParseBench VLM rows are auto-matched as single models

ParseBench rows in categories starting with VLM (proprietary or open-weight) are single models and may be auto-matched to an introducing paper. Parsing products and PDF libraries are pipelines, so they are published only with a hand-reviewed paper or release identity.

Code: `backend/services/parsebench_sync_service.py::MODEL_CATEGORY_PREFIX`

## Open ASR discovery tolerates model IDs that are not Hub repos

Proprietary Open ASR entries can use display names, for example a preview linked to a documentation Space, that are not valid Hugging Face model IDs. Discovery records an HFValidationError as an unavailable model and continues instead of failing the run.

Code: `backend/services/open_asr_sync_service.py::OpenAsrPaperDiscoveryService`

## Open ASR language rows match English rows by exact then Hub id

The English and multilingual Open ASR views spell some model ids differently, e.g. "org/m (runtime)" versus "org/m". Matching tries exact upstream ids first, then the suffix-stripped Hub id, so language rows reuse the English row's paper and metadata without exact ids being shadowed.

Code: `backend/services/open_asr_language_sync_service.py::OpenAsrLanguageSyncService._english_models`

## Open ASR language sync accepts both Average ER and Average WER

The Open ASR Space renamed "Average WER" to "Average ER" on 2026-11-13 because a few languages such as Chinese report CER. Every language synced here reports WER, so for a single selected language both column labels are read as that language's WER; adding a CER language would require a different metric.

Code: `backend/services/open_asr_language_sync_service.py`

## Open ASR legacy importer rows are replaced by live sync rows

Rows created by the retired one-shot Open ASR importer are deleted once a valid live table has been processed, because the live rows that replace them are authoritative. Deletion happens only after validation so a bad fetch cannot wipe the board.

Code: `backend/services/open_asr_sync_service.py::OpenAsrSyncService.sync`

## Open ASR model cell badges are stripped before identity matching

Since 2026-11-13 the Open ASR leaderboard appends badge spans such as an 'Open weights' marker after the model link. These are display markers, not part of the model identity, so model_cell strips them before the model ID is derived; otherwise every model would appear renamed.

Code: `backend/services/open_asr_sync_service.py::_BADGE_RE`

## Open ASR openness is inferred from Hub model links

The multilingual Open ASR view has no license column, so is_open is first inferred from whether the model link points to the Hugging Face Hub (proprietary APIs link to vendor docs) and later refined from the English board's license where that board lists the model.

Code: `backend/services/open_asr_language_sync_service.py::parse_language_table`

## Open ASR runtime variants collapse to one row per Hub model

The Open ASR leaderboard appends the inference runtime, for example '(fast-gpu-asr)', to a Hub model ID and lists several runtime variants per model. The sync strips the suffix to get the Hub ID and keeps one row per Hub model; when upstream's best runtime variant changes, the new variant takes over the existing row and its paper binding.

Managed Open ASR rows are indexed by both full upstream model ID and Hub model ID, so when upstream's best runtime variant changes the new variant updates the existing row and inherits its paper instead of creating a duplicate.

Code: `backend/services/open_asr_sync_service.py::_RUNTIME_SUFFIX_RE`, `backend/services/open_asr_sync_service.py::OpenAsrSyncService.sync`

## Open ASR sync accepts the tuple-shaped Gradio table response

Since 2026-10-28 the Open ASR Space's main table endpoint returns a (table update, plot update) tuple instead of a single component update. The parser takes the first element when given a sequence and then unwraps the headers/data value, so both response shapes parse.

Code: `backend/services/open_asr_sync_service.py::_leaderboard_value`

## Open ASR sync recalculates both WER and RTFx ranks

Live Open ASR rows carry RTFx throughput as well as WER, and preserved paper-native rows may use throughput as their primary metric. After syncing, ranks are recalculated for both metrics so those rows stay correctly ordered.

Code: `backend/services/open_asr_sync_service.py::OpenAsrSyncService.sync`

## Open ASR sync requests the License column only for open/proprietary status

The Open ASR leaderboard's License column is requested so the sync can mark each model open or proprietary. It is a text column, so it never enters the computed WER average over the numeric dataset columns.

Code: `backend/services/open_asr_sync_service.py::LICENSE_COLUMN`

## Open TTS all-languages board averages only the core languages

Seed-TTS and CV3-Eval cover a fixed set of core languages. On 2026-11-12 the MiniMax dataset added languages only it covers, which let a single model rank across every language. The all-languages board therefore averages over CORE_LANGUAGES only, keeping its averages comparable.

Code: `backend/services/open_tts_sync_service.py::CORE_LANGUAGES`

## Open TTS keeps one best-ranked row per model across voices

The Open TTS leaderboard can list the same model several times under different voices. The parser keeps only the best-ranked row per model ID so a model appears once on the board.

Code: `backend/services/open_tts_sync_service.py::parse_open_tts_leaderboard`

## Open TTS per-language boards exclude English default and Cantonese

Per-language Open TTS boards map each Space language label to its ?languages=<code> deeplink. English is served by the default board rather than a separate one, and Cantonese is omitted because too few models rank on it to form a meaningful leaderboard.

Code: `backend/services/open_tts_sync_service.py::LANGUAGE_BOARDS`

## Open TTS publishes only models with a dedicated arXiv paper

The Open TTS model catalog was reviewed against the model cards linked from the default leaderboard on 2026-09-11. Only models with a dedicated arXiv paper are published as leaderboard rows; others are left to the shared matcher or release radar.

Code: `backend/services/open_tts_sync_service.py::MODEL_CATALOG`

## Open TTS setup treats the first BENCHMARKS entry as the parent board

The Open TTS setup script makes the first dataset it upserts the parent and attaches every later one as a subset variant. BENCHMARKS must therefore list the English board first; reordering it silently re-parents the language boards.

Code: `backend/database/datasets_setup/add_open_tts_leaderboard.py::main`

## Open TTS skips unranked rows with partial coverage

The Open TTS leaderboard leaves Rank empty for models that do not cover every selected language and dataset, because their averages are not comparable. The parser skips those rows instead of importing their averages.

Code: `backend/services/open_tts_sync_service.py::parse_open_tts_leaderboard`

## ParseBench provider labels are a reviewed trust boundary

Each ParseBench row is published only when its exact upstream Provider label maps to a reviewed introducing paper or official release page (or is a VLM row matched automatically). Unreviewed labels stay unpublished and are reported by the job; deliberate exclusions (parsing products and libraries with no paper or release page) are listed separately so they are not reported as unreviewed.

Each ParseBench row is published only when its exact upstream Provider label maps to a reviewed introducing paper or official release page. Some labels share a page, e.g. KDL-Frontier-Parser-nano-v2 has no release page of its own and KoreaDeep publishes it as the next version of the nano parser, so it maps to the nano release.

Labels without an introducing paper or official release page are excluded after review. For example Upstage Document Parse 2 (Enhanced) is the API snapshot document-parse-260930 and Upstage publishes only a changelog entry, so it is excluded rather than attached to a weak source.

Code: `backend/services/parsebench_sync_service.py::MODEL_PAPER_IDENTITIES`, `backend/services/parsebench_sync_service.py::EXCLUDED_PROVIDERS`

## ParseBench syncs from the upstream leaderboard CSV

Both the ParseBench README top-10 table and parsebench.ai are rendered from leaderboard.csv in the run-llama/parsebench repository. The sync reads that CSV directly rather than scraping either rendered view, so it sees the full board in a stable format.

Code: `backend/services/parsebench_sync_service.py::PARSEBENCH_CSV_URL`

## ParseBench-2 is synced as a separate benchmark

ParseBench-2 has its own CSV, six dimensions and different provider label conventions (e.g. "Claude Opus 5.5" rather than "Anthropic Opus 5.5"). It is synced as its own dataset with its own reviewed identity map rather than as a lane of ParseBench, and its v2 CSV has no HF_Model_ID column, so Hub checkpoints for open-weight rows are recorded in the reviewed map.

Code: `backend/services/parsebench_sync_service.py::PARSEBENCH_2_CSV_URL`, `backend/services/parsebench_sync_service.py::PARSEBENCH_2_MODELS`

## Physics-IQ Verified keeps reviewed unrounded scores

The Physics-IQ Verified sync was validated against 33 rows hand-imported and reviewed on 2026-10-13. Physis-Lang keeps the unrounded score submitted in its upstream PR even though the official README lists it at one decimal, so sync comparisons must tolerate the rounding difference and must not overwrite the reviewed value with the rounded README figure.

Code: `backend/tests/evaluation/test_physics_iq_verified_sync.py::PRODUCTION_ROWS`

## Physics-IQ Verified rows import only through reviewed exact labels

The Physics-IQ Verified sync maps each README leaderboard row to its introducing paper only through MODEL_IDENTITIES, keyed by the exact plain-text label (links reduced to text, <small> notes kept in parentheses) and track. Unreviewed labels are reported, never imported. Several labels may map to one model when the leaderboard lists more than one single-generation run of it, and only the best run is published. Prompt-upsampling variants (for example FLUX 3 or GPT-6 Astra rewritten prompts) map to the underlying model because only the prompts change; a best-of-N reranker counts as part of the model only when it is the paper's own contribution (GeoPhys), while third-party rerankers such as WMReward are excluded.

Code: `backend/services/physics_iq_verified_sync_service.py::MODEL_IDENTITIES`

## Physics-IQ Verified syncs from the GitHub README

physics-iq-verified.anates.ai renders its table from data compiled into its Next.js bundle and exposes no JSON endpoint, so the sync parses the google-deepmind/physics-IQ-benchmark README as the canonical source of the leaderboard.

Code: `backend/services/physics_iq_verified_sync_service.py::PHYSICS_IQ_README_URL`

## Physics-IQ sync refuses tracks whose reviewed subset collapses

Besides overall row-count bounds, the Physics-IQ Verified sync requires at least 20 reviewed i2v rows and 5 reviewed v2v rows before it updates that track. If upstream relabels rows so the reviewed subset collapses, the track is left untouched rather than having most of its leaderboard deleted.

Code: `backend/services/physics_iq_verified_sync_service.py::MIN_SELECTED_BY_TRACK`

## Physics-IQ: Wan 2.2 attributed to the Wan paper

Wan 2.2 has no technical report of its own and its README cites the original Wan paper (arXiv 2503.20314), so Physics-IQ Verified rows for Wan 2.2 are attached to that paper.

Code: `backend/services/physics_iq_verified_sync_service.py::MODEL_IDENTITIES`

## Qwen 3.6 Max maps to Qwen3.6-Max-Preview

Qwen3.6-Max only shipped as a preview release, so the board's 'Qwen 3.6 Max' row is linked to the Qwen3.6-Max-Preview identity and its blog post. Creating a non-preview Qwen3.6-Max model would invent a release that does not exist.

Code: `backend/services/carbon_board_identities.py::IDENTITIES`

## RSI-Exam sync is pinned to one reviewed release

RSI-Exam normalised scores are rescaled whenever the benchmark ships a new release or task set. The sync pins the release name and task count and refuses to run when the page no longer names that release. A reviewer then decides whether the managed leaderboard rows move to the new scale, instead of silently mixing incomparable scores.

Code: `backend/services/rsi_exam_sync_service.py::RELEASE`

## Reasoning-effort variants collapse to the best score per model and paper

Third-party boards list the same language model several times at different reasoning-effort settings. The sync strips the effort suffix and keeps only the best-scoring setting per (paper, model), recording lower settings as collapsed, so a leaderboard never shows one model several times.

Code: `backend/services/artificial_analysis_decision_sync_service.py::DecisionIndexSyncService.sync`

## Reasoning-effort variants share one leaderboard model

Labels with a reasoning-effort suffix such as '(max)' or '(xhigh)' name the same model as their base. Their rows share the base name, so the board keeps only that model's best setting rather than listing each effort level as a separate model.

Code: `backend/services/leaderboard_model_matching_service.py::LeaderboardModelMatcher.match`

## Retired Artificial Analysis TTS slugs delete their managed rows

Slugs in RETIRED_MODEL_SLUGS were reviewed as gone upstream (404 and absent from the full catalog), so their managed leaderboard rows are deleted. st260629 was retired on 2026-09-09 while the separate step-audio-2.5-tts version remains live and must not inherit it; vibe-voice-7b was retired on 2026-11-19 while vibe-voice-1-5b keeps its own row.

Code: `backend/services/artificial_analysis_tts_sync_service.py::RETIRED_MODEL_SLUGS`

## Reviewed paper bindings override carried-over rows

When the Open ASR sync has a reviewed arXiv paper for a model, it rebinds rows carried over from the legacy importer to that paper. Without a reviewed entry it keeps the existing row's paper, which may have been curated by hand, rather than resetting it.

Code: `backend/services/open_asr_sync_service.py::OpenAsrSyncService.sync`

## Riemann-Bench scores come from visible text, not data-score

The Riemann-Bench page renders an empty `data-score` attribute; the percentage is only present in the visible text of the score cell's parent. The parser reads that text instead of the attribute.

Code: `backend/services/carbon_board_syncs.py::parse_riemann_bench`

## Rows of a fully withdrawn index are kept until scores return

When Artificial Analysis returns no scores at all for an index (as with Agentic on 2026-10-29), the sync records it as withdrawn and keeps the existing leaderboard rows instead of retiring them. An empty index is treated as an upstream outage rather than a signal that every model was removed.

Code: `backend/services/artificial_analysis_sync_service.py::ArtificialAnalysisLeaderboard`

## SLE Hypothesis Discovery rows are attributed to the DiscoveryRSI harness

Sciences' Last Exam runs Hypothesis Discovery in its own DiscoveryRSI research harness, not in the coding-agent harness the site lists for each model. The sync labels those rows with DiscoveryRSI so the harness shown on Papers with Code matches the setup that produced the score.

Code: `backend/services/sle_sync_service.py::HYPOTHESIS_HARNESS`

## SLE composite membership is pinned and reviewed

The SLE composite score averages a fixed set of assessments. Adding a new assessment upstream restates every composite, so the sync pins the member list and a reviewer must decide before managed composite rows change scale.

Code: `backend/services/sle_sync_service.py::COMPOSITE_MEMBERS`

## SLE trailing asterisks mark provisional composites

The Sciences' Last Exam site appends an asterisk to a model name when its composite is provisional. The parser strips it from the label and instead derives provisional status from the per-assessment results, so the same model is not treated as two distinct names.

Code: `backend/services/sle_sync_service.py::parse_leaderboard`

## SWE-Marathon configs without reasoning effort are treated as max

The SWE-Marathon site treats a model configuration with no reasoning effort as maximum effort. The sync uses DEFAULT_EFFORT='max' for such rows so effort-based selection and labels match what the site shows.

Code: `backend/services/swe_marathon_sync_service.py`

## SWE-Marathon only ranks complete runs

A SWE-Marathon run counts as complete only if it covers every task with the board's standard trial count, taken as the most common per-task trial count across runs. Partial runs are excluded so pass@1 is compared on equal footing.

Code: `backend/services/swe_marathon_sync_service.py::parse_swe_marathon_bundle`

## SWE-Marathon sync does not adopt self-reported vendor rows

Vendor self-reported SWE-Marathon results (for example Kimi K3.1 Pro) are kept as unmanaged rows next to the benchmark authors' runs. The sync is configured with adopt_unmanaged=False so it neither takes them over nor deletes them.

Code: `backend/services/swe_marathon_sync_service.py`

## SWE-Marathon sync refuses to run when too few entries are selected

If upstream changes shrink the reviewed, selected subset below MIN_SELECTED_ENTRIES (15), the SWE-Marathon sync refuses to touch the managed leaderboard. This prevents a parser break or upstream regression from deleting most of the board's rows.

Code: `backend/services/swe_marathon_sync_service.py`

## Stored unrounded scores are kept when they match the board

A reviewer may have stored a more precise value (48.23) than the upstream board lists (48.2). The live sync keeps the stored value when it rounds to the listed one and does not count it as a change; only a real difference replaces it with the board's value.

Code: `backend/services/live_leaderboard_sync.py::LiveLeaderboardSyncService.sync`

## Surge AI boards are fetched with a browser user agent

Surge AI's Webflow host rejects requests with non-browser user agents. The Riemann-Bench fetcher reuses `surge_chartography.USER_AGENT` (a browser string) for that reason; dropping it makes the sync fail with HTTP errors.

Code: `backend/services/carbon_board_syncs.py`

## Surge Chartography is fetched with a browser-like user agent

The Surge benchmark page is hosted on Webflow, which rejects non-browser user agents. The sync sends a Chrome-style user agent string, suffixed with a paperswithcode identifier, so the fetch succeeds.

Code: `backend/services/surge_chartography_sync_service.py::USER_AGENT`

## Surge Chartography model labels are a reviewed trust boundary

Exact Surge model labels (provider plus model, without reasoning configuration) are mapped by hand to the catalog model name and its introducing paper or release page, reviewed against the rows originally hand-imported. Labels not in the map are matched automatically only when the catalog names them unambiguously, and otherwise handed to the release radar instead of published.

Exact Surge model labels are mapped by hand to the catalog model and its release source. Some labels need non-obvious mappings, e.g. Surge's 'Qwen 3.8 Flash' is the Qwen Cloud API version of the open-weight Qwen3.8-Flash-Next, so it maps to that Hub release.

Code: `backend/services/surge_chartography_sync_service.py::MODEL_IDENTITIES`

## Surge Chartography sync writes only the no-tools benchmark

Surge evaluates Chartography without tools, so its sync writes only the chartography-no-tools dataset and suffixes model names with (no tools). The separate with-tools chartography benchmark is curated by hand from vendor model cards and must never be modified by the sync.

Code: `backend/services/surge_chartography_sync_service.py::DATASET_SLUG`

## TabArena imputed scores do not set uses_additional_data

TabArena imputes missing benchmark scores. That imputation is an estimation step, not evidence the model used extra training data, so synced rows always set uses_additional_data = False.

Code: `backend/services/tabarena_sync_service.py::TabArenaSyncService.sync`

## TabArena links resolve to arXiv papers only through curated mappings

TabArena entry links that point at another canonical surface (Nature, GitHub, OpenReview) map to a local arXiv paper only through the exact-URL URL_ARXIV_OVERRIDES table. All other non-arXiv links resolve only through curated source, repository, project-page or Hugging Face artifact associations in the database, never by fuzzy matching.

Code: `backend/services/tabarena_sync_service.py::URL_ARXIV_OVERRIDES`

## TabArena separates unknown models from missing arXiv papers

Entries whose link has no indexed paper go to the shared leaderboard model matcher, and unmatched ones become release-radar signals. An entry whose arXiv paper is simply not indexed is reported as a catalog gap rather than an unknown model.

Code: `backend/services/tabarena_sync_service.py::TabArenaSyncService.sync`

## Task tagging tracks papers in memory because the session does not autoflush

Several Artificial Analysis slugs can map to the same paper. The session runs without autoflush, so a PaperTask added earlier in the loop is invisible to the existence query. The sync keeps a tagged_paper_ids set to avoid inserting duplicate paper-task rows.

Code: `backend/services/artificial_analysis_sync_service.py::ArtificialAnalysisSyncService.sync`

## Tencent Hy4 maps to the full release, not Hy4 Preview

The board's 'Tencent Hy4' row is the full Hy4 release of 2026-11-04, not the August Hy4 Preview. It is linked to the full release announcement and marked open; reusing the preview identity would merge two different models.

Code: `backend/services/carbon_board_identities.py::IDENTITIES`

## Terminal-Bench-Science sync does not adopt vendor-run rows

The Terminal-Bench-Science board also carries vendors' own runs (Claude Code, unnamed harnesses) that the Artificial Analysis feed does not manage. The sync sets `adopt_unmanaged=False` so those rows are left as they are rather than being taken over or removed by the independent-evaluation sync.

Code: `backend/services/carbon_board_syncs.py`

## Third-party leaderboard syncs bind to papers only through reviewed exact upstream IDs

Display labels on external leaderboards are not reliable enough to pick a canonical release paper. Syncs such as ARC Prize and the Artificial Analysis Decision Index keep a reviewed map from exact upstream group, model or contestant IDs to paper identities; anything else goes through the shared model-release matcher or is reported as unmatched and surfaced as a release-radar signal rather than guessed.

The Artificial Analysis Decision Index sync keeps reviewed contestant slugs ('<host>_<model>') mapped to canonical papers. Other contestants bind through the model-release catalog matcher or are reported as release-radar signals until a paper exists.

The Open ASR sync keeps an exact, reviewed map from Hub model IDs to arXiv papers. Models without a defensible paper stay unmatched rather than being bound by guesswork; rows carried over from the legacy importer supplied continuity for the first live synchronization.

ProgramBench sync maps exact upstream run IDs to reviewed official release pages. Displayed model labels are not trusted, and new runs stay unpublished until their model identity has been reviewed and added to the map.

Code: `backend/services/arc_prize_sync_service.py::SELECTOR_PAPER_IDENTITIES`, `backend/services/artificial_analysis_decision_sync_service.py::MODEL_PAPER_IDENTITIES`, `backend/services/open_asr_sync_service.py::MODEL_PAPER_ARXIV_IDS`, `backend/services/programbench_sync_service.py::MODEL_PAPER_IDENTITIES`

## Third-party rerun boards do not adopt hand-imported rows

By default a live leaderboard sync adopts a hand-imported row for the same paper and model name and makes it managed, keeping the reviewer's methodology as notes beneath the managed head. Boards that are third-party reruns set adopt_unmanaged to False, because their scores must sit beside the paper's self-reported rows instead of overwriting them.

Code: `backend/services/live_leaderboard_sync.py::LiveLeaderboard`, `backend/services/live_leaderboard_sync.py::LiveLeaderboardSyncService.sync`

## Title-matched models are open only with linked own weights

For models matched to an announcing paper without a reviewed release, is_open is set only when the paper links a Hugging Face repository holding that model's own weights. Linking some other artifact or none leaves the row closed.

Code: `backend/services/leaderboard_model_matching_service.py::LeaderboardModelMatcher.match`

## Unmatched leaderboard models become release-radar signals

New single-model rows on a live leaderboard are matched to an indexed paper by LeaderboardModelMatcher. Rows with no match are not dropped or guessed; they become release-radar signals so the paper can be indexed, and the row is published on a later sync run once it matches.

Code: `backend/services/extractbench_sync_service.py::ExtractBenchSyncService.sync`

## Upstream slug renames carry bindings only for managed rows

Artificial Analysis occasionally renames model slugs. The sync keeps a reviewed map of exact old-to-new slugs, and only rows the sync previously managed may carry their existing paper binding across a rename. Manually curated rows and conflicting bindings are left for review rather than silently rebound.

Code: `backend/services/artificial_analysis_sync_service.py::MODEL_SLUG_RENAMES`

## Vals Finance Agent parser checks only the leading header columns

Vals periodically relabels the cost and duration columns of the Finance Agent v2 table (on 2026-10-26 they became "Tokens / Test" and "Duration / Test"). The parser validates and reads only the leading Rank / Model / Accuracy columns so such relabels do not break the sync, while still failing on changes to the columns it uses.

Code: `backend/services/vals_finance_agent_sync_service.py::TABLE_HEADER`

## Vals model labels map to papers only through an explicit identity table

A Vals leaderboard row is linked to its introducing paper only via an exact match on the Vals model label in a reviewed identity table, with display names following the PwC catalog rather than Vals' spelling. Other labels are linked automatically only when the catalog names them unambiguously; anything else is handed to the model release radar instead of being guessed.

Code: `backend/services/vals_finance_agent_sync_service.py`

## Vals v1.1 re-run rows reuse the reviewed Vals Index identities

The Vals board was re-run on the v1.1 answer keys on 2026-11-02. Model identities for the re-run rows deliberately follow the already reviewed Vals Index rows for the same models, so the same model is not created twice with different names or sources.

Code: `backend/services/carbon_board_identities.py::IDENTITIES`

## Variant benchmark names carry their chip label in parentheses

Benchmark variants are named "<root name> (<label>)", and the frontend variantLabel helper derives the chip label shown under the parent board from that parenthesised suffix. Open ASR language boards are therefore named "Open ASR Leaderboard (<language>)" with the English board as parent; renaming them without the suffix breaks the chip labels.

Code: `backend/database/datasets_setup/add_open_asr_language_leaderboards.py::main`

## Vending-Bench 2 parser accepts both object-literal and JSON.parse encodings

Andon Labs' Vending-Bench 2 site shipped run data as a minified object literal (`vb2:{`) before 2026-11-02 and as a JSON.parse string (`"vb2":{`) since. The `_VB2_RUNS` pattern matches both forms so the sync survives either build of the site.

Code: `backend/services/carbon_board_syncs.py::_VB2_RUNS`

## Vending-Bench 2 route node is resolved through hydration node_ids

Since 2026-11-02 the Vending-Bench 2 SvelteKit page preloads only its layout nodes. The route's own node, which imports the chunk holding run data, is named only by the hydration `node_ids` and must be resolved through the app entry's node table. The fetcher therefore downloads the app entry and follows those node ids in addition to the preloaded `/nodes/` scripts.

Code: `backend/services/carbon_board_syncs.py::fetch_vending_bench_2`

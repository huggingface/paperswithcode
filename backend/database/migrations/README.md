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
| `add_organization_logo_sha256.sql` | Content-addressed immutable organization logo URLs |
| `add_paper_organization_provenance.sql` + `run_add_paper_organization_provenance.py` | Authenticated HF-user provenance for manually curated paper/organization links |
| `add_paper_relations.sql` + `run_add_paper_relations.py` | `paper_relations` table |
| `add_paper_redirects.sql` | Shared redirects for papers merged into canonical ArXiv rows |
| `add_pending_paper_edits.sql` + `run_add_pending_paper_edits.py` | pending edit queue |
| `add_security_hardening_submissions.sql` | Stable-subject submission provenance, applied/result review audit fields, idempotency/rate-limit indexes, user profiles/aliases, and suspension state |
| `allow_taxonomy_suggestions_without_paper.sql` | nullable paper association for suggestions submitted from taxonomy directories |
| `add_conference_suggestion_edit_type.sql` | conference suggestions submitted from the conference directory |
| `add_organization_suggestion_edit_type.sql` | `new_organization` suggestions (name, HF handle, website, logo) submitted from the paper organizations dialog; apply as `postgres` for `public`, then again with `search_path=staging,public`, before deploying |
| `add_auto_approved_review_kind.sql` | Allows `pending_paper_edits.reviewed_by_kind = 'auto'` for edits applied immediately and reviewed afterwards on `/submissions`; apply as `postgres` for `public`, then again with `search_path=staging,public`, before deploying |
| `add_paper_x_threads.sql` | Paper-scoped `paper_x_threads` previews for the paper-page X threads card plus the `x_threads` pending-edit type; apply as `postgres` for `public`, then again with `search_path=staging,public`, before deploying code that reads the table |
| `add_benchmark_gap_review.sql` | Review state and audit `resolution` on `benchmark_curation_candidates`, plus `paper_curation_jobs.benchmark_candidate_id` and the `review-benchmark-gaps`/`add-benchmark` kinds for the daily `enqueue_benchmark_gap_review` CRON; apply as `postgres` (updates the `staging` copies too) before deploying |
| `add_benchmark_gap_review_scope.sql` | `paper_curation_jobs.review_scope`: the candidate batch a `review-benchmark-gaps` job was served and must decide; apply as `postgres` (updates `staging` too) before deploying |
| `add_model_release_signals.sql` | `model_release_signals` plus `paper_curation_jobs.release_signal_id` and the `model-release-radar` trigger, so `scan_model_releases` can queue a `resolve-model-paper` job per unindexed release; apply as `postgres` (adds the job column to `staging` too) before deploying |
| `add_paper_suggested_questions.sql` | `paper_suggested_questions`: three cached Luna starter questions per paper, generated lazily by `GET /papers/{id}/suggested-questions` (staging gets INSERT too); apply as `postgres` before deploying |
| `add_single_benchmark_board_guard.sql` | Deferred `evaluations_single_benchmark_board` trigger: a benchmark's leaderboard for a metric lives on one task, so a row that would leave a copy under a second task is rejected at commit (whole-board moves in one transaction still pass; the migration refuses to install while splits remain); `benchmark_task_board_exceptions` lists approved same-metric boards with a different protocol; apply as `postgres` |
| `add_paper_abstract_mentions.sql` | `abstract_linking` mode and `aliases` on `methods`/`datasets`/`frameworks`, plus `paper_abstract_mentions` for linked catalog names in abstracts (staging gets SELECT); apply as `postgres` before deploying code that maps the columns |
| `add_research_topics.sql` | `research_topics` (shared free-text topics with backfill state), `research_topic_verdicts` (raw Jev scores per topic and paper), and `research_subscriptions.topic_id`/`topic_set_at`, with staging copies; apply as `postgres` before deploying code that maps the columns |
| `add_author_google_scholar_profiles.sql` | `author_google_scholar_profiles`: verified Google Scholar profile per author with its paper-overlap evidence, shown on author pages and filled by the weekly `link_google_scholar_profiles` CRON (staging gets SELECT); apply as `postgres` before deploying code that reads the table |
| `add_author_google_scholar_candidates.sql` | `author_google_scholar_candidates`: Semantic Scholar and Scholar-profile evidence per Wikidata candidate, the progress of the weekly `link_google_scholar_profiles` CRON; apply as `postgres` before deploying |
| `add_user_bookmarks.sql` + `run_add_user_bookmarks.py` | user bookmarks |
| `add_chat_sessions.sql` | Authenticated chat sessions, UI messages, and opaque Agent SDK transcript storage |
| `add_chat_primary_paper.sql` | Common chat-session primary-paper binding plus durable reader-context snapshots; apply to each enabled environment before activating code that uses the shared chat ORM |
| `add_chat_paper_selection.sql` | Staging-only additive `chat_messages.paper_selection` snapshot for Highlight and Ask; apply with `search_path=staging,public` before activating ORM code that maps the column |
| `add_chat_session_archiving.sql` | Non-destructive bulk archiving for old chats and the active-chat quota |
| `add_chat_edit_preparation_state.sql` | Typed durable fork identity used to recover interrupted chat edits |
| `add_chat_sandbox_runtime.sql` | Staging-only additive immutable chat backend selection, runtime provenance, sandbox leases, and hash-only turn capabilities; run as PostgreSQL superuser with `search_path=staging,public` before activating the bridge |
| `add_chat_external_worker_registry.sql` | Additive durable identity, capacity, heartbeat, graceful-drain state, and fencing generations for trusted external Pi workers; apply to staging before enabling the external-worker shadow supervisor |
| `add_chat_turn_jobs.sql` | Additive durable per-turn ownership, immediate admission, idempotency, worker lease fencing, and interruption state; apply to staging before enabling `PWC_CHAT_DURABLE_TURN_DISPATCH_ENABLED` |
| `add_chat_executor_registrations.sql` | Fenced persistent-executor manifests, cells, shards, registrations, nonces, claims, key revocations, and append-only rollback audit; apply first with the target environment schema selected |
| `add_chat_turn_reservations.sql` | Environment-global 32-turn/128-operation capacity and bounded incremental spend reservations for persistent executor admission; apply after executor registrations with the same environment schema selected |
| `add_chat_executor_transport_circuit.sql` | Immutable per-turn legacy/persistent selection plus a shared rollout circuit and durable alert-epoch claims; apply after turn reservations and before enabling remote transport |
| `add_chat_turn_terminal_cleanup_index.sql` | Add the partial terminal replay-journal cleanup index before enabling durable terminal maintenance |
| `add_chat_turn_latency.sql` | Staging-only, content-free per-turn server/browser latency telemetry with 30-day application retention; apply after `add_chat_sandbox_runtime.sql` |
| `add_chat_sandbox_pool.sql` | Staging-only blank-worker pool lifecycle, generation binding, resource/cost accounting, and 35-day audit state; apply with `search_path=staging,public` before deploying pool-aware readiness |
| `add_chat_warm_assignment_race.sql` | Additive health-probe ownership and content-free warm-fallback diagnostics for either environment-owned chat schema; apply before deploying the warm-assignment race fix |
| `add_chat_sandbox_egress_policy.sql` | Staging-only `egress_policy_digest` on sandbox leases and the blank pool so reviewed MCP host allowlists cannot reuse incompatible sandboxes; apply with `search_path=staging,public` before deploying worker contract 83 |
| `add_chat_sandbox_spend_cap.sql` | Staging-only append-only full sandbox lifecycle meter, monthly circuit state, and deduplicated operator event ledger |
| `add_chat_title_budget.sql` | Environment-owned, persistent monthly reservation/reconciliation ledger and alert events for the independent staging and production $25 server-funded title circuits |
| `add_chat_shares.sql` | Staging-only self-contained public chat capability snapshots and durable assistant finish reasons; run as PostgreSQL superuser with `search_path=staging,public` before activating chat sharing |
| `add_chat_artifacts.sql` | Staging-only typed-artifact base rows retained for the private-paper foundation and historical compatibility; apply before `expand_chat_artifact_foundation.sql`. Posterly remains disabled. |
| `expand_chat_artifact_foundation.sql` (rollback: `rollback_expand_chat_artifact_foundation.sql`) | Additive typed-artifact foundation for disabled private LaTeX papers: allowed kind, paper-only immutable version metadata, and independent source/preview heads; apply after `add_chat_artifacts.sql` before later paper-feature migrations |
| `allow_chat_latex_paper_restore_digests.sql` | Permit repeated source digests when restoring a historical paper snapshot as a new immutable version; apply after `expand_chat_artifact_foundation.sql` before enabling restore |
| `add_chat_latex_paper_figure_storage.sql` | Additive content-addressed private PNG/JPEG/PDF figure blobs and immutable version references; apply after `expand_chat_artifact_foundation.sql` before enabling paper figure uploads |
| `add_chat_latex_repair_provenance.sql` | Add selected-model provenance to successful immutable LaTeX repair versions; apply after `expand_chat_artifact_foundation.sql` before enabling AI repair |
| `add_chat_openrouter_user_budget.sql` | Staging-owned per-HF-user funded OpenRouter monthly aggregates and provider-call ledger, AES-256-GCM BYOK records, bounded non-secret audit events, and capability revision/error fields; apply with `search_path=staging,public` before enabling any OpenRouter model |
| `add_chat_direct_openai.sql` | Staging-only direct-OpenAI capability mode plus per-owner funded usage reservations, exact Responses usage settlement, and unknown-cost reconciliation ledger; apply with `search_path=staging,public` before enabling the direct route |
| `add_chat_medium_reasoning_effort.sql` / `add_chat_medium_reasoning_effort_production.sql` | Widen the staging (`search_path=staging,public`) and production (`public`) chat reasoning-effort checks to accept `medium`; apply before deploying a backend that defaults chats to medium |
| `add_paper_curation_jobs.sql` | durable admin-triggered Hugging Face paper-curation Jobs |
| `add_curation_bootstrap_bundle_store.sql` | `paper_curation_bootstrap_bundles`: one content-addressed bootstrap snapshot per distinct bundle, referenced by `paper_curation_jobs.bootstrap_bundle_sha256` instead of a ~100 KB copy per job; apply as `postgres` before deploying (backfilled 2026-10-28) |
| `drop_curation_legacy_bootstrap_bundle.sql` | Drops the emptied legacy `paper_curation_jobs.bootstrap_bundle`; apply as `postgres` only after the release that no longer maps it is live, and it refuses while any job still holds a bundle |
| `add_autonomous_paper_curation.sql` | two-stage HF daily workflows, trace provenance, scheduler state, and benchmark-gap backlog |
| `add_autonomous_operations.sql` | Fail-closed operator controls, immutable run/action evidence, global repair lease, provider state, attempt budgets, and Codex execution accounting |
| `add_autonomous_release_broker.sql` | Root-owned single-use exact-SHA deploy/rollback authorization consumption |
| `add_autonomous_submission_claims.sql` + `add_autonomous_submission_remote_jobs.sql` | Existing-taxonomy submission claims, scoped callbacks, and remote HF Job lifecycle state |
| `add_autonomous_alert_delivery.sql` | Append-only, content-free, deduplicated urgent/mobile delivery receipts |
| `add_autonomous_acceptance_evidence.sql` | Append-only rollout gate evidence and idempotency index |
| `add_curation_autonomous_operator.sql` | Add the disabled curation operator and widen its autonomous ledger and alert-receipt constraints; apply after the autonomous operations and alert-delivery migrations |
| `add_curation_thumbnail_queue.sql` | transactionally queued, CRON-owned thumbnail work and accepted-submission state for paper-curation Jobs |
| `add_external_resources_schema.sql` + `run_add_external_resources_schema.py` | external resources |
| `add_trending_score.sql` + `run_add_trending_score.py` + `update_trending_view_for_ema.sql` | repository (GitHub) trending scores |
| `add_paper_hf_trending.sql` + `run_add_paper_hf_trending.py` | composite paper trending: `hf_artifacts`, `paper_hf_artifacts`, and `papers.trending_score`/components (rollback: `rollback_paper_hf_trending.sql`) |
| `add_dataset_variants_and_splits.sql` + `run_add_dataset_variants_and_splits.py` | dataset variants (rollback: `rollback_dataset_variants_and_splits.sql`) |
| `add_keywords_to_methods.sql` | methods keywords column (rollback: `rollback_keywords_from_methods.sql`) |
| `add_evaluations_num_parameters.sql` | `evaluations.num_parameters` |
| `add_evaluations_harness.sql` | `evaluations.harness` |
| `add_evaluations_hf_model_url.sql` | `evaluations.hf_model_url` |
| `add_evaluations_source_attribution.sql` | `evaluations.source_url` and `evaluations.external` |
| `add_evaluation_badge_tombstones.sql` | Durable public badge targets for deleted evaluation rows |
| `add_task_datasets_supports_harness.sql` | `task_datasets.supports_harness` |
| `remove_task_datasets_featured_rank.sql` | Remove obsolete manual benchmark pinning; task pages use benchmark trends |
| `add_task_sister_tasks.sql` + `run_add_task_sister_tasks.py` | `task_sister_tasks` table (explicit sister tasks) |
| `add_task_recommended_frameworks.sql` | Ordered task-to-repository framework recommendations, with initial image-classification and object-detection data |
| `add_framework_catalog.sql` | First-class framework domains, categories, entities, platforms, canonical papers, repositories, and task links |
| `add_embedding_models_frameworks.sql` | Sentence Transformers and Text Embeddings Inference catalog entries plus ordered Embedding models task recommendations |
| `add_nemo_speech_framework.sql` | NVIDIA NeMo Speech catalog entry plus recommendations for its supported speech and audio tasks |
| `add_paper_tasks_source.sql` | `paper_tasks.source` |
| `add_methods_scanned_at_to_papers.sql` | `papers.methods_scanned_at` |
| `add_method_source_paper_id.sql` | `methods.source_paper_id` |
| `add_method_link_provenance.sql` | method-link evidence, exclusions, and resumable keyword/reference backfill state |
| `add_paper_performance_indexes.sql` | paper query indexes |
| `add_author_filter_indexes.sql` | exact normalized author-name and Hugging Face username lookup indexes |
| `add_missing_dataset_variant_fields.sql` | dataset variant columns |
| `cleanup_obsolete_hidden_tasks.sql` | Preconditioned removal of five obsolete tasks, six low-impact benchmarks, and their explicitly audited links/evaluations |
| `add_entity_search_vectors.sql` + `backfill_entity_search_vectors.py` + `add_entity_search_indexes.sql` | Name-only benchmark, method, and task search vectors, triggers, and GIN/trigram indexes |
| `remove_tasks_is_visible.sql` | Remove retired task visibility state after the production compatibility gate |
| `add_chat_active_cost.sql` | Add requested-resource and estimated active-turn cost fields to staging chat latency telemetry |
| `add_chat_external_worker_reservations.sql` | Add protected pre-admission capacity reservations for exact external worker claims |
| `add_chat_qualification_evidence_events.sql` | Create or forward-repair staging/production qualification scopes and content-free cohort events, including exact FKs/checks/indexes and cascade retention cleanup; apply before qualification metadata |
| `add_chat_qualification_metadata.sql` | Bind latency rows to a server-issued qualification scope/profile and install the exact scope/admission-time index; apply after qualification evidence scopes |
| `repair_chat_qualification_evidence_contract.sql` | Final additive qualification repair: exact defaults, primary/foreign/unique/check/index contracts plus per-turn workload metadata; apply after both qualification migrations and refuse lossy populated conversions |
| `add_chat_turn_latency_qualification_compatibility_production.sql` | Production-only nullable compatibility columns mapped by shared chat latency telemetry while external-Pi qualification remains disabled; apply before deploying source that maps scope/profile/workload |

Before running `remove_task_datasets_featured_rank.sql`, deploy application
code without `featured_rank` into both the current and previous release slots
for staging and production. This keeps the immediate rollback releases
compatible after the column is dropped.

Do not run `remove_tasks_is_visible.sql` until visibility-free source is live
in both the production current and immediate rollback releases. The additive
entity-search schema and bounded backfill can be applied before that gate.

## Adding new migrations

- **Schema changes**: add idempotent SQL here; add a `run_*.py` wrapper when
  post-apply verification or service calls are needed (see `run_add_trending_score.py`).
- **Method / benchmark / task / eval curation**: do not add one-off SQL files — use
  `.agents/skills/add-method/`, `add-task/`, `add-benchmark/`, or `add-evals/` instead.

No Alembic. Migrations are applied manually on the VPS with `psql` or `uv run`.

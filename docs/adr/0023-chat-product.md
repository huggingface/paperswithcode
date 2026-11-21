# ADR 0023: Research chat product surfaces

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## Alert evidence files rely on directory permissions

Operational alert evidence files are written world-readable (0644) so the dashboard can read them; confidentiality comes from the parent directory being traversable only by the production service group. Moving the files to a less restricted directory would expose them.

Code: `backend/scripts/monitor_chat_operational_alerts.py::write_health_record`

## Alert monitor persists state before delivery

The alert monitor writes its journal cursor and pending events to disk before any Slack or network delivery. If delivery crashes or hangs, the next run resumes from the saved cursor without losing or re-collecting events.

Code: `backend/scripts/monitor_chat_operational_alerts.py::main`

## App instance IDs allow 200 characters

MCP App instance IDs reuse worker tool call IDs. OpenAI Responses call IDs take the form call_<id>|fc_<id> and run to about 90 characters, so the bound matches ToolDisplayBlock.id at 200 characters rather than assuming a UUID.

Code: `backend/models/chat.py::AppDisplayBlock`

## Catalog vocabulary biasing applies only to the OpenAI fallback

Dictation biases transcription towards catalog vocabulary (model, method and dataset names) via a prompt. Voxtral's realtime API has no prompt field, so the VOCABULARY prompt is only sent to the OpenAI realtime fallback.

Code: `backend/services/dictation_service.py`

## Chat SQLite tests compensate for PostgreSQL-only behavior

Chat repository tests run on SQLite, which ignores PostgreSQL partial-index predicates and drops timezone information. Fixtures drop idx_chat_messages_current_revision (otherwise its user-revision uniqueness would apply to assistant rows) and restore timezone-aware loaded values with set_committed_value so tests match PostgreSQL behavior.

Code: `backend/tests/chat/test_feedback_service.py::db`, `backend/tests/chat/test_turn_job_repository.py::test_stale_session_cannot_overwrite_a_newer_committed_terminal`

## Chats with private papers cannot be shared

Model output in a paper turn can legitimately quote failed sources or diagnostics. Rather than attempting to sanitize such output for a public snapshot, any chat with a private paper artifact or paper block is owner-only for its whole lifecycle and share creation is refused.

Code: `backend/services/chat_share_service.py::ChatShareService.create_or_refresh`

## Closing a live stream leaves durable completion to the coordinator

With durable turn dispatch, the dispatch coordinator owns turn completion. Closing the live stream source before terminal persistence completes only releases admission; it must not mark the turn complete or drop its lease.

Code: `backend/services/chat_stream_service.py::ChatStreamOrchestrator._close`

## Compile reconciliation re-reads each version under the artifact lock

Reconciliation first selects a bounded list of pending versions without locks, then takes the same per-artifact transaction lock used by owner polls and writes before re-reading each version. Another worker may have settled, deleted or reattached the job in between, so decisions are made only on the locked re-read.

Code: `backend/services/latex_paper_service.py::LatexPaperService.reconcile_pending_compiles`

## Compile transport failures requeue the version for reconciliation

If fetching a compile result fails with a network error or the compiler restarts, the version is set back to queued with a transport_failure diagnostic instead of being marked failed. The bounded operator reconciliation later retries it, so transient outages never produce false compile failures.

Code: `backend/services/latex_paper_service.py::LatexPaperService._compile`

## Dictation max-model-len 2304 caps sessions at about two minutes

Voxtral Realtime consumes roughly 17 audio tokens per second, so --max-model-len 2304 corresponds to about two minutes of audio and acts as the server-side session length cap. Changing the value changes the maximum dictation length.

Code: `backend/cli_dictation.py::SERVER_ARGS`

## Dictation vLLM image is built by a public build-only Space

The Voxtral dictation endpoint image is built from deploy/dictation/Dockerfile by the public, build-only Space nielsr/pwc-voxtral-vllm. Hugging Face Inference Endpoints cannot pull images from private Spaces, so the build Space must stay public; making it private breaks endpoint deployment.

Code: `backend/cli_dictation.py::DEFAULT_IMAGE`

## Edit transcript cleanup failures are logged, not raised

After an edit is activated, deleting the superseded agent transcript is best-effort. A failure is logged as a leak and does not undo the activated edit.

Code: `backend/services/chat_stream_service.py::_prepare_replacement`

## Expired-job reconciliation repairs one legacy state

Older telemetry cleanup could mark a conversation interrupted with lease_expired without closing its durable job. Reconciliation repairs only that exact expired state and leaves any other mismatch untouched.

Code: `backend/services/chat_turn_admission_coordinator.py::ChatTurnAdmissionCoordinator._reconcile_expired_claims`

## Failed cancellation lookup reports not-cancelled

When checking durable cancellation during error handling, a database error is treated as not cancelled so the original turn failure is preserved instead of being replaced by the lookup error.

Code: `backend/services/chat_stream_service.py::ChatStreamOrchestrator._cancel_requested_after_error`

## Feedback export failures never fail the rating

Chat feedback is stored in PostgreSQL first and that row is the record. Export to the tracing backend is a diagnostic mirror, so any export failure is logged and leaves exported_to unset instead of failing the user's rating request.

Code: `backend/services/chat_feedback_service.py::ChatFeedbackService._export`

## Feedback without a trace is stored but not exported

Langfuse scores must attach to a trace. A chat rating whose message has no trace_id is stored in the database only and never exported.

Code: `backend/tests/chat/test_feedback_service.py::test_feedback_is_stored_even_without_trace_correlation`

## Figure blob deletion is deferred until the reference removal commits

Deleting a LaTeX project or version removes figure blob references in the database first and queues storage-prefix cleanup to run only after that transaction commits. A concurrent upload therefore cannot deduplicate onto a blob that is about to be deleted; failed object deletions stay queued for reconcile_storage_cleanup.

Code: `backend/tests/latex_papers/service/test_figures.py::test_deleting_unreferenced_versions_and_project_reclaims_only_orphaned_figures`

## File placeholders are recognized on their own line inside text

The Pi harness sends the whole user prompt as a single text part, so a user-file placeholder may stand on its own line inside longer text. Only placeholders alone on a line are expanded; inline mentions are left as text.

Code: `backend/services/chat_provider_gateway/user_files.py::PLACEHOLDER_LINE`

## Hot GitHub trending runs on the host timer, not GitHub Actions

Scheduled execution of the hot GitHub trending update runs on the production host's systemd timer (pwc-cron-update-hot-github-trending.timer). The GitHub Actions workflow keeps only workflow_dispatch for manual recovery and must not regain a schedule, which would run the job twice.

Code: `backend/tests/deployment/test_cron_environment.py::test_hot_workflow_runs_on_the_activated_production_schedule`

## Human source versions become the source head before compiling

When a human saves a LaTeX version, the artifact's source head is advanced before compilation starts. A failed compile therefore remains a durable, repairable version, while the preview continues to show the last successfully compiled PDF.

Code: `backend/services/latex_paper_service.py::LatexPaperService.save_human_version`

## LaTeX compiles have a per-owner aggregate budget

Every LaTeX compile starts a fresh paid provider sandbox. On top of per-job limits, each owner may have at most 2 active compiles and 100 compiles per day; repair candidates are capped per failed version, which these version counts bound in turn, so total sandbox spend per owner is bounded.

Code: `backend/services/latex_paper_service.py::_MAX_ACTIVE_COMPILES_PER_OWNER`

## LaTeX paper artifacts track source and preview heads independently

source_head_version_id and preview_head_version_id are independent: a failed LaTeX source keeps the prior successful preview without associating that PDF with the new source. Both stay NULL for legacy and current Posterly rows.

Code: `backend/models/database/chat_artifacts.py::ChatArtifact`

## LaTeX symbol table is ordered longest name first

_math_segment_to_plain replaces \\name commands with Unicode by sequential str.replace over _LATEX_MATH_SYMBOLS. Names that are prefixes of others (phi/varphi, epsilon/varepsilon) would corrupt longer commands if replaced first, so the table must list longer names before shorter ones.

Code: `backend/utils/latex_text.py::_LATEX_MATH_SYMBOLS`

## Latency expiry skips turns owned by durable jobs

Turns with a nonterminal durable job are expired only by the durable lifecycle, which updates the job and conversation atomically under the worker's current lease. The session's active-turn lease can lapse while that worker is healthy, so session-lease expiry must not mark those turns failed.

Code: `backend/services/chat_latency_service.py::ChatLatencyService.reconcile_stale_turns`

## Launcher dumpability test runs in a subprocess

cron_launcher.hide_launcher_environment marks the calling process non-dumpable (prctl PR_SET_DUMPABLE 0) so same-user jobs cannot read its environment. The test calls it in a child Python process and checks prctl(3) (PR_GET_DUMPABLE) there, keeping the pytest process itself dumpable.

The probe calls prctl option 3, which is PR_GET_DUMPABLE; a result of 0 confirms hide_launcher_environment made the process non-dumpable.

Code: `backend/tests/deployment/test_cron_environment.py::test_launcher_hides_its_environment_from_same_user_jobs`

## Legacy v1 search fields stay on tool-call records

Stored chat history from the local_mcp backend uses the v1 search projection with hits and results fields on tool calls. These optional fields are retained so old messages still validate and render; they can only be removed once local_mcp history is retired.

Code: `backend/models/chat.py::ToolDisplayBlock`

## MCP App checkpoint IDs are owner-only

MCP App results may carry a checkpointId in structuredContent. It is retained only in the owner's projection; the public-share projection strips it before data leaves the authenticated session, so any new share path must also remove it.

Code: `backend/models/chat.py::McpAppResult`

## Old shared artifacts are flushed before reinsert

Shared artifact rows are unique per share and identifier. Deleted rows are flushed before inserting the replacement snapshot so the unique constraint does not fire; a later failure rolls back both.

Code: `backend/services/chat_share_service.py::ChatShareService._materialize_artifacts`

## Old shares fall back to the session's selected model

Share snapshots created before model attribution do not contain the public-safe model field. For those, the model is read from the source session's selected_model so existing share URLs keep showing a model.

Code: `backend/services/chat_share_service.py::ChatShareService.get_public`

## One bucket storage client per process

The HF bucket storage client is cached per bucket and token so each process reuses one client, keeping its HTTP connections and Xet session warm. Constructing a client per request adds connection and session setup latency to every upload and read.

Code: `backend/services/chat_file_service.py::_bucket_storage`

## Only a committed journal write authorizes worker replay pruning

after_persist callbacks run only after the journal transaction commits. Socket sends and queue admission never authorize the worker to prune its replay buffer, so a crash before commit can still be replayed.

Code: `backend/services/chat_detached_turn_service.py::DetachedTurnCoordinator._append_batch`

## Only the latest user turn can block a session

Continuations preserve earlier failed turns as history. A session needs recovery only when its latest user message is interrupted or errored; a completed continuation unblocks chat.

Code: `backend/services/chat_session_service.py::ChatSessionService._has_unresolved_turn`

## OpenAI file ID is committed immediately after upload

The OpenAI file ID is the only handle that can delete the uploaded OpenAI copy, so it is committed to the row as soon as both writes succeed. If the chat was deleted meanwhile the commit fails, and the error path removes both copies.

Code: `backend/services/chat_file_service.py::ChatFileService.upload`

## Orchestrator survives terminal persistence failure

If writing a turn's terminal state fails, the orchestrator is kept registered so a later persistence_error fallback can still write a durable terminal; only the external reservation is released.

Code: `backend/services/chat_detached_runtime.py::ChatDetachedRuntime._persist_terminal`

## PDF probe sets rlimits in the child, not via preexec_fn

The PDF probe applies RLIMIT_AS and RLIMIT_CPU inside the child process rather than with subprocess preexec_fn, because preexec_fn can deadlock when the parent (a threaded FastAPI worker) forks.

Code: `backend/services/chat_file_probe.py::_main`

## Paper deletion tolerates failed sandbox cancellation

When a LaTeX paper is deleted, pending provider jobs are cancelled best-effort: cancellation errors are logged and ignored. The provider VMs are disposable, and failing the delete would strand the user's chat on an unreachable sandbox.

Code: `backend/services/latex_paper_service.py::LatexPaperService._cancel_pending_provider_jobs`

## Persisted projection shape stays pinned across Pi image changes

Releases that change the Pi image keep an explicit persisted-shape test for the chat projection, so the rollback window always contains two releases whose readers are qualified against the same stored block order.

Code: `backend/tests/chat/test_message_projection.py::test_chat_projection_preserves_sse_block_order`

## Project deletion queries versions instead of the loaded relationship

The SQLAlchemy identity map can still hold already-deleted historical version rows. delete_project queries the durable set of versions from the database so storage cleanup only follows live references.

Code: `backend/services/latex_paper_service.py::LatexPaperService.delete_project`

## Projection mismatches fail closed only for their owner

An expired durable turn whose projection mismatches is recorded and left untouched. Admission fails closed only for the account that owns it, so one corrupt record cannot block admission for other users.

Code: `backend/services/chat_turn_admission_coordinator.py::ChatTurnAdmissionCoordinator._report_projection_mismatch`

## Repair candidates are ephemeral until they compile successfully

Automatic repair attempts are not persisted as durable versions or jobs until a candidate finishes compiling successfully and its preview fits the owner's quota. Any pending per-job sandbox for an unfinished candidate is cancelled, since no durable record exists to reconcile it later, and failed candidates never become durable failed sources.

Code: `backend/services/latex_paper_service.py::LatexPaperService.repair_failed_version`

## SPA shell hiding rule precedes all head links

The SPA shell hides the server-rendered initial documents with an inline rule. Vite injects the app stylesheet after the existing head links at build time, so the hiding rule must appear before the first <link> (and before any <script>) to take effect before the stylesheet loads; otherwise initial documents flash visibly.

Code: `backend/tests/deployment/test_nginx.py::test_spa_shell_never_reveals_initial_documents`

## SQLite-backed chat tests restore timezone info

SQLite drops timezone information on datetime columns while PostgreSQL keeps it. SQLite-backed tests that compare against aware datetimes reattach UTC to loaded values; removing that patch causes naive/aware comparison errors that do not occur in production.

Code: `backend/tests/chat/test_admission_expiry_transaction.py::test_same_session_retry_respects_live_durable_lease.owned_with_utc`

## Saved-progress retries keep the original request text

A saved-progress retry keeps the original displayed request alongside its augmented effective prompt, because mode selection, lease duration and idempotent replay all key on the original text.

Code: `backend/services/chat_session_service.py::ChatSessionService.begin_turn`

## Shared App blocks get fresh instance IDs and no checkpoint

A public share is a browser-local fork. App blocks in a share get a new random instance ID, are marked public_fork, and have structuredContent emptied, so the share never hands out the owner's checkpoint or an App/session correlation capability.

Code: `backend/services/chat_share_service.py::_public_blocks`

## Shares and paper creation share an advisory lock

Share creation takes the same pg_advisory_xact_lock key as LaTeX paper creation for the session. A share that starts first is a pre-paper immutable snapshot; a share that starts after a paper insert sees the artifact and fails closed. Changing either key breaks this exclusion.

Code: `backend/services/chat_share_service.py::ChatShareService.create_or_refresh`

## Stored Posterly cards stay readable when generation is disabled

Posterly artifact flags gate generation only. Historical safe PNG cards already stored remain readable when the generation flags are off, so read paths must not check chat_artifacts_enabled or chat_posterly_enabled.

Code: `backend/chat_configuration/settings.py::ChatArtifactSettings`

## The source-version UUID is the compile idempotency key

Compile jobs are submitted with the immutable source-version UUID as job id. A fresh backend process, a Space restart or a lost/finished dedicated VM can resubmit the same bundle under that id without creating a second logical compile job, so replacing an ended VM is safe.

Code: `backend/services/latex_paper_service.py::LatexPaperService.refresh_compile`, `backend/services/latex_paper_service.py::LatexPaperService._compile`

## Title generation disables reasoning on OpenRouter

Chat titles are a cosmetic, bounded extraction with a 64-token budget. DeepSeek's low reasoning mode can spend that whole budget before emitting any title text, so OpenRouter title requests set reasoning effort to none.

Code: `backend/services/chat_title_service.py::stream_title`

## Traces carry uploaded-file metadata, not contents

Provider-request traces record only uploaded-file metadata. Audits read file contents from PwC's private store by id, so file contents never go to the tracing backend.

Code: `backend/services/chat_tracing_service.py::start_provider_request_trace`

## Unreported dictation sessions expire after max length plus grace

A connected dictation session that never reports back would otherwise count against live capacity forever. It stops counting as live after the maximum session length plus LIVE_GRACE_SECONDS, which leaves time for the final transcript to arrive.

Code: `backend/services/dictation_service.py`

## Uploaded chat files are stored privately for audits; OpenAI holds the model copy

File uploads are supported only for direct Luna. PwC keeps its own copy in a private bucket for chat-health audits, while the model reads the copy uploaded to OpenAI by file_id. Audits read our copy; traces carry only metadata.

Code: `backend/chat_configuration/settings.py::ChatArtifactSettings`

## User file placeholders are refused on non-OpenAI providers

Uploaded files exist only as OpenAI file_ids. When uploads are enabled, the Messages protocol refuses payloads that still contain user-file placeholders rather than forwarding them to a provider that cannot resolve them.

Code: `backend/services/chat_provider_gateway/anthropic_messages.py::AnthropicMessagesProtocol.prepare`

## chat_turn_latency backend CHECK has an auto-generated deployed name

The deployed backend CHECK on chat_turn_latency is the auto-named inline constraint from add_chat_turn_latency.sql (chat_turn_latency_execution_backend_check), not the ORM's explicit name. Migrations changing it must drop both names; dropping only the ORM name is a silent no-op.

Code: `backend/tests/chat/test_latency_service.py::test_external_pi_backend_migration_is_environment_scoped`

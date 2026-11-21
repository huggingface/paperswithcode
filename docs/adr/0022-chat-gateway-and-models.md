# ADR 0022: Research chat gateway, models and budgets

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## Admission reserves up to four real tokens per metered OpenAI token

The gateway meters OpenAI input as JSON bytes / 4, which can undercount real tokens. Turn admission therefore prices each metered token at up to four actual tokens at long-context rates (input and cache-write x8, output x1.5) so the reservation is a true upper bound.

Code: `backend/services/chat_executor_turn_admission.py::maximum_provider_turn_microusd`

## All historical routes keep a provider mapping

Issued chat capabilities carry an immutable route, and new turns pick routes from current settings. During a rolling provider switch, and for routes from the retired comparison registry, both old and new routes keep a provider mapping even though they are hidden from discovery, so already-issued capabilities stay serviceable. Dropping a mapping breaks in-flight or persisted capabilities.

Code: `backend/chat_configuration/registry.py::route_providers`

## Ambiguous-dispatch boundary is committed before calling the provider

The ledger marks a call dispatched and commits before any bytes reach the provider. A crash after that point retains the full reserved bound instead of under-counting spend for a call that may have run.

Code: `backend/services/chat_provider_gateway/lifecycle.py::ProviderCallLifecycle.run`

## App calls produce no generic tool block

An MCP App block owns its diagram input, so a create_view call produces only the App block and no generic tool block, avoiding a duplicate accordion in the UI.

Code: `backend/services/chat_stream_service.py::ChatTurnProjection._start_app`

## Capability row lock is released before provider network checks

Capability validation takes a row lock so concurrent SDK model calls get distinct request counters. The lifecycle commits that bounded mutation before any provider or budget network lookup; otherwise a slow lookup holds the lock and blocks sibling model calls.

Code: `backend/services/chat_provider_gateway/lifecycle.py::ProviderCallLifecycle._meter`

## Chat calls are funded at the full output ceiling

The minimum fundable OpenRouter call is priced at the normal MAX_OUTPUT_TOKENS ceiling plus request and input fees. When a user's remaining budget is smaller, the call is refused rather than silently lowering output or quality settings to fit.

Code: `backend/services/openrouter_user_budget_service.py::minimum_fundable_call_microusd`

## Chat gateway calls its environment's MCP release over loopback

Each environment runs its own MCP component on a dedicated loopback port, and staging must exercise the staging release rather than production. The gateway connects to the loopback listener directly without the nginx hop so the MCP server accepts the X-PwC-MCP-Client header and rate-limits each chat session separately.

Code: `backend/services/chat_pwc_mcp.py::ENDPOINTS`

## Direct OpenAI admission is serialized by one environment-wide advisory lock

Concurrency, rate, daily and monthly admission checks for direct OpenAI run under a single pg_advisory_xact_lock keyed by environment, so gateway processes cannot race past a limit. Splitting the lock per limit would reintroduce check-then-act races.

Code: `backend/services/chat_openai_budget_service.py::ChatOpenAIBudgetService._enforce_limits`

## Excalidraw App HTML is pinned to a reviewed digest

The Excalidraw MCP App runs in an iframe next to private diagram content. Every environment fetches the App shell only if it matches the reviewed SHA-256 digest from WORKER_MCP_PROVIDERS and never serves upstream changes directly, so an upstream compromise cannot reach users without review.

Code: `backend/routers/chat.py::excalidraw_app_html`

## Expiry tracking ignores malformed pricing dates

Malformed pinned-pricing verification dates are reported by startup validation. The expiry tracker returns no expiry for them rather than raising, so the expiry monitor never crashes on config that validation already flags.

Code: `backend/services/chat_config_expiry.py::_pricing_expiry`

## Finished live streams linger 30 seconds

After a live chat stream ends, the registry keeps it for 30 seconds before removal. This covers the race between the terminal SSE frame and the browser's canonical session reload, so a reconnect in that window still finds the stream.

Code: `backend/services/chat_live_stream_service.py::LiveChatStreamRegistry._expire`

## GLM-5.3-Flash is hidden from production discovery while direct Luna serves

When direct OpenAI Luna serves production, production model discovery exposes only Luna; GLM-5.3-Flash is hidden and its sessions continue on Luna.

Code: `backend/services/runtime_policies/chat_provider.py::validate_chat_provider_policy`

## Gateway authorizes and meters before reading the request body

The provider lifecycle authenticates and meters the capability token and turn once before reading or decoding a body of up to 8 MiB, then binds the parsed model to the capability without metering again. Reading the body first would let unauthenticated callers force large reads.

Code: `backend/services/chat_provider_gateway/lifecycle.py::ProviderCallLifecycle.run`

## Gateway forwards only an allowlist of Anthropic Messages fields

Workers may send only the listed Anthropic Messages fields. OpenRouter extensions (model/route fallbacks, plugins, transforms, provider) would let a turn select routes or paid features the funded ledger never priced, so they are dropped and logged; the server itself sets user, provider and reasoning.

Code: `backend/services/chat_provider_gateway/anthropic_messages.py::ANTHROPIC_REQUEST_FIELDS`

## Gateway lifecycle logs under backend.chat_gateway_app

The provider lifecycle module logs under the gateway's logger name, backend.chat_gateway_app, rather than __name__, because operational log matching and alerting key on that name. Renaming the logger silently breaks them.

Code: `backend/services/chat_provider_gateway/lifecycle.py::logger`

## Gateway releases the request DB session before streaming from the provider

A FastAPI yield dependency would hold the request's DB connection until the StreamingResponse finishes. At fleet concurrency that exhausts the pool while calls merely wait on providers, so the lifecycle closes the session before the upstream request and uses short-lived sessions for later accounting.

Code: `backend/services/chat_provider_gateway/lifecycle.py::ProviderCallLifecycle.run`

## Global abuse circuit check is serialized with a Postgres advisory lock

The OpenRouter abuse circuit checks global spend across all users. A transaction-scoped pg_advisory_xact_lock serializes that check with the reservation insert across users and workers, while each user's monthly usage row serializes that user's own reservations.

Code: `backend/services/openrouter_user_budget_service.py::OpenRouterUserBudgetService._enforce_abuse_circuit`

## Historical Luna ID in the alternative-model flag is ignored

The staging alternative-model flag may still hold the historical ID openai/gpt-5.6-luna. Luna now has its own explicit OpenRouter choice, so that value is ignored rather than adding a second, misleadingly named Luna entry; the old ID stays only as a hidden route alias.

Code: `backend/chat_configuration/registry.py::chat_model_records`

## Hugging Face Inference Provider routes pin a named provider, never :fastest

The `:fastest` suffix on Hugging Face Inference Providers routes hops across backends per request and has included providers with broken model mappings. Every reviewed route therefore pins one live provider (e.g. `:baseten`, `:novita`). Changing a route to `:fastest` reintroduces nondeterministic, possibly broken serving.

The `:fastest` suffix on Hugging Face Inference Providers routes hops across backends per request and has included providers with broken model mappings. Every reviewed route therefore pins one live provider. Changing a route to `:fastest` reintroduces nondeterministic, possibly broken serving.

Code: `backend/chat_configuration/settings.py::ChatModelSettings`

## Layout Markdown failure falls back to canonical Markdown

Page-aware layout Markdown only adds citations. Any failure reading it is logged and the reader falls back to canonical OCR Markdown rather than failing the turn.

Code: `backend/services/chat_paper_context_service.py::ChatPaperContextService._load`

## Long-context OpenAI turns are priced at a multiplier

Direct OpenAI usage over the long-context threshold is priced at 2x the input rate, including cached and cache-write input categories, and 1.5x the output rate. Budget reservations and actual-usage settlement must apply the same multipliers.

Code: `backend/tests/chat_budget/test_direct_openai.py::test_direct_openai_pricing_uses_per_million_rates_and_fails_stale`

## MCP disconnect polling uses an explicit finished event

The client-disconnect probe may absorb task cancellation inside its own cancel scope, so cancelling it is not a reliable stop signal. The gateway sets an independent finished event before cancelling and joining the call and disconnect tasks, which guarantees the polling loop exits and the join cannot hang.

Code: `backend/chat_gateway_app.py::catalog_mcp`

## Messages protocol TTFT measures first body byte

For the Anthropic Messages protocol, the gateway records time to first token at the first response body byte rather than parsing for the first token delta. Latency comparisons with the Responses protocol must account for this.

Code: `backend/services/chat_provider_gateway/anthropic_messages.py::MessagesUsageStream.feed`

## Model card downloads are refused above 1 MiB

Only MAX_CARD_TOTAL_BYTES of a model card is read, but the download itself happens first. Cards larger than MAX_CARD_DOWNLOAD_BYTES (1 MiB) are refused so a huge file cannot fill the backend's limited disk before any limit applies.

Code: `backend/services/chat_hf_hub_service.py::MAX_CARD_DOWNLOAD_BYTES`

## Model card front matter with YAML aliases is rejected

YAML aliases let a small document expand multiplicatively when copied. Model cards have no use for them, so front matter containing any alias event is marked malformed instead of loaded.

Code: `backend/services/chat_hf_hub_service.py::_split_card`

## Monthly chat budget limit is snapshotted per bucket

Each user's monthly usage row snapshots the budget limit when created. Changing the configured limit only affects newly created monthly buckets; existing months keep their limit, which is logged when it differs.

Code: `backend/services/openrouter_user_budget_service.py::OpenRouterUserBudgetService.reserve_call`

## Only tool outputs and validated catalog results seed fetchable URLs

URLs the model may fetch are seeded from Bash/Read/Grep output and the validated search_papers catalog projection. WebFetch and web-search result blocks are excluded so fetched pages cannot widen the fetch allowlist.

Code: `backend/services/chat_session_service.py::ChatSessionService.fetchable_url_seed`

## OpenAI context and long-context thresholds come from the GPT-6 Luna model page

MAX_BILLABLE_INPUT_TOKENS (1,050,000) and LONG_CONTEXT_INPUT_THRESHOLD (272,000) are taken from OpenAI's GPT-6 Luna model documentation (https://developers.openai.com/api/docs/models/gpt-6-luna) and must be updated from there when the model changes.

Code: `backend/services/chat_openai_budget_service.py::MAX_BILLABLE_INPUT_TOKENS`

## OpenRouter receives only an opaque owner identifier

The `user` field sent to OpenRouter is an opaque per-owner value derived server-side; it supports reconciliation but cannot identify the Hugging Face subject.

Code: `backend/services/chat_provider_gateway/anthropic_messages.py::AnthropicMessagesProtocol.prepare`

## Org-funded Hugging Face routes never carry the user's token

Sponsored routes are billed to the organization at the gateway. For hf_org_funded routes the user's Hugging Face credential is not placed in the turn capability, so it cannot be used or billed.

Code: `backend/services/chat_turn_runner.py::create_chat_turn_runner`

## Overflowing entries are pushed back to the queue front

queue.Queue has no push-front, so an entry that would overflow the current POST is reinserted at the front of the underlying deque under the queue mutex. get() does not touch unfinished_tasks, so no adjustment is made; the batch that later carries the entry calls task_done for it.

Code: `backend/services/chat_trackio_service.py::TrackioClient._requeue_front`

## Paper loads coalesce per route and PDF-fallback mode

In-flight paper context loads are coalesced by route and by whether PDF fallback is allowed. Reader loads, which may download the PDF, and metadata-only loads never wait on or inherit each other's result, and a reader follower reloads itself if the leader found nothing.

Code: `backend/services/chat_paper_context_service.py::_PreparedPaperCache.prepare`

## Persisted route IDs are immutable; only their served model may change

Sessions and capabilities persist the public route ID. The historical Luna route stays OpenRouter-backed so sessions carrying the old ID never switch providers, and the direct OpenAI route ID stays fixed while the model it serves (gpt-6-luna) changes. Renaming a route ID orphans or reroutes existing sessions.

Sessions and capabilities persist the public route ID. The direct OpenAI route ID stays fixed while the model it serves (gpt-6-luna) changes. Renaming a route ID orphans or reroutes existing sessions.

Code: `backend/chat_configuration/settings.py::ChatModelSettings`

## Persisted tool blocks drop raw argument fragments

Live rendering streams raw tool-argument JSON fragments, which may contain secrets before they parse. Persisted tool blocks keep only the bounded, sanitized authoritative snapshot and drop argument_text and argument_state; running tools are stored as errors.

Code: `backend/services/chat_stream_service.py::ChatTurnProjection.completed_blocks`

## Pi and funded OpenRouter sessions always use the gateway backend

Trusted cost extraction and per-call reservation exist only at the private gateway, so sessions on the Pi harness or a funded OpenRouter route always use the modal_cli backend regardless of rollout percentages; they must never run on local_mcp.

Code: `backend/services/chat_session_service.py::ChatSessionService.create_session`

## Poster tool arguments stream as sanitized snapshots

Raw tool-argument JSON fragments can contain a secret before they become parseable and redactable. Poster streams therefore replace deltas with a sanitized, replaceable snapshot of the parsed arguments instead of forwarding raw fragments.

Code: `backend/services/chat_stream_service.py::_public_poster_tool_event`

## Pricing freshness is enforced per request, not at startup

OpenRouter pricing freshness depends on the wall clock. It is checked per request, so affected routes fail closed, rather than in startup validation, where an expired pricing date would stop every worker and take down the whole site.

Code: `backend/services/runtime_policies/chat_provider.py::_validate_chat_openrouter_policy`

## Production validates OpenRouter accounting without requiring the shared key

Production's OpenAI and HF routes do not use the shared OpenRouter key, so it is required only when server-funded OpenRouter is enabled; durable accounting validation still runs for existing sessions and BYOK.

Code: `backend/services/runtime_policies/chat_provider.py::_validate_chat_openrouter_policy`

## ProviderError with no HTTP error relays the upstream response

A ProviderError whose `error` is None records its code but relays the upstream response unchanged; a non-None error replaces the response with the gateway's own HTTP error.

Code: `backend/services/chat_provider_gateway/lifecycle.py::ProviderError`

## Queue-full drop logs are rate-limited but keep the alert prefix

Trackio queue-full drops come in bursts, so only the first per interval is logged, with the count of suppressed drops. The log line must keep the 'chat Trackio trace dropped' prefix that the operational alert monitor matches, and it includes only the hashed trace ID, never chat content. The method must be called with the service lock held.

Code: `backend/services/chat_trackio_service.py::TrackioClient._drop_queue_full`

## Raw tracing sees events before trust checks and sanitization

Every turn event is recorded to raw tracing before artifact-receipt trust checks and public sanitization run. _project_event is the single public display and persistence boundary, so sanitization must happen there and not before tracing, otherwise diagnostics lose the raw event.

Code: `backend/services/chat_stream_service.py::ChatStreamOrchestrator._project_event`, `backend/services/chat_stream_service.py::ChatStreamOrchestrator._consume`

## Reader paper cursor falls through to untagged Markdown

For page-capped layouts, the cursor after the last tagged chunk uses the `layout-untagged:` prefix; following it reads the untagged stored Markdown through the hosted MCP from the start, so the model can read pages the layout did not tag.

Code: `backend/services/chat_reader_paper_read.py::UNTAGGED_CURSOR_PREFIX`

## Reader read_paper serves page-tagged text

In reader chat, read_paper for the primary paper returns the page-tagged text that the answer's page citations reference, not the untagged stored Markdown. Serving Markdown would make citations unverifiable. Cursors with the untagged prefix opt out and fall back to the normal path.

Code: `backend/chat_gateway_app.py::catalog_mcp`

## Reservation rejection details are computed after rollback

Some rejection details read accounting state that is valid only after the failed reservation is rolled back, so ProviderReservationRejected stores a callable detail and evaluates it when building the HTTP error.

Code: `backend/services/chat_provider_gateway/lifecycle.py::ProviderReservationRejected.http_error`

## Retired model IDs stay routable but hidden

Chat sessions persist the selected model ID, and older sessions carry IDs from registries that no longer offer those models. Those IDs are kept as hidden aliases that resolve to the canonical DeepSeek route and never appear in model discovery. Removing an alias breaks resuming old sessions.

Code: `backend/chat_configuration/registry.py::LEGACY_SELECTED_MODEL_IDS`

## Retired model routes stay as read-only settings for old sessions

Sessions persist the model route they were created with. Routes retired from discovery (GLM 5.2, Gemma, GLM 5.3 Flash) remain as settings so those sessions still resolve, but they are never exposed in current model discovery. Removing them breaks existing sessions.

Code: `backend/chat_configuration/settings.py::ChatModelSettings`

## Retired sponsored route keeps org billing

Capabilities are issued with an immutable route and may outlive the switch that disables the sponsored DeepSeek model. The sponsored route therefore stays mapped to hf_org_funded billing so in-flight turns keep charging the organization and never fall through to user billing.

Code: `backend/chat_configuration/registry.py::route_funding_modes`

## Runtime alert patterns match content-free log lines only

RUNTIME_FAILURE_PATTERNS match log strings that are emitted without prompts, answers, capabilities or credentials, so alerts can quote them safely. Provider failures are excluded here because they alert from a sustained database signal instead.

Code: `backend/services/chat_operational_alert_service.py::RUNTIME_FAILURE_PATTERNS`

## SSE streams start with a padding comment

Some edge POPs buffer small initial HTTP/2 DATA frames even when origin and nginx disable buffering. Each chat SSE stream therefore begins with an ignored comment padded above the common 2 KiB threshold, forcing intermediaries to flush before the first model delta and protecting time to first token.

Code: `backend/routers/chat.py::stream_chat.event_stream`

## Scope guardrail uses its own credentials and counters

The research-scope guardrail is server-owned: its HF token, bill-to, limits and counters are deliberately separate from user inference credentials and from the direct-OpenAI chat allowance. Reusing user or chat-allowance credentials would let guardrail traffic consume user budget or let user traffic exhaust the guardrail.

Code: `backend/chat_configuration/settings.py::ChatScopeGuardrailSettings`

## Semantic Scholar search paths are listed once for metering

Credentialed Semantic Scholar keyword searches are metered against the turn's direct-search allowance. SEARCH_PATHS is the single list of such paths; adding a search endpoint elsewhere would bypass metering.

Code: `backend/services/chat_semantic_scholar_service.py::SEARCH_PATHS`

## Sponsored DeepSeek is billed to the HF organization and pinned to Novita

The free DeepSeek V4.1 Flash route for signed-in users is billed to the Hugging Face organization behind the title credential; that organization's Inference Providers spending limit is the only budget, so the application cap reserves nothing for it. Only Novita serves the pinned snapshot, so the route is fixed to `:novita` and runtime validation rejects any other route.

The free DeepSeek route is bounded by the Hugging Face organization's Inference Providers spending limit, so sponsored and user-billed HF routes reserve nothing from the application spend cap at turn admission.

Code: `backend/chat_configuration/settings.py::ChatModelSettings`, `backend/services/chat_executor_turn_admission.py::maximum_provider_turn_microusd`

## Luna failover replays once on the sponsored route and reports only Luna's errors

When direct OpenAI fails before a Luna turn shows any output, the worker may replay the turn once on the sponsored DeepSeek route, but only on a route this turn's runner offered; a worker's failover claim alone changes nothing. The runner issues a second, credential-free capability for that route because the gateway bills the organization. The session keeps Luna selected and only the turn's assistant row records the model that answered. Errors from the fallback capability, such as an exhausted sponsorship, are not actionable for a user who chose Luna, so the user sees only the primary route's error code. The fallback route stays out of model discovery.

Code: `backend/services/chat_stream_service.py::ChatTurnProjection._record_provider_failover`, `backend/services/chat_turn_runner.py`, `backend/services/runtime_policies/chat_provider.py::validate_chat_provider_policy`

## Sponsored mode is set per provider call, not on the capability

Sponsored DeepSeek calls are recorded with provider mode hf_org_funded at call level only; the persisted capability row keeps provider_mode "huggingface". Writing the sponsored mode to the capability would change how existing capabilities resolve.

Code: `backend/services/chat_provider_gateway/anthropic_messages.py::AnthropicMessagesProtocol.prepare`

## Staging defaults to direct Luna for paper qualification

The first discoverable record is the default model. On staging with direct OpenAI enabled, the direct GPT-6 Luna route is placed first because staging paper qualification is measured against it; the other routes remain selectable for comparative testing and existing sessions. Reordering the tuple silently changes what staging qualification measures.

Code: `backend/chat_configuration/registry.py::chat_model_records`

## Stale-call recovery waits a minute after the turn terminates

Recovery of dispatched OpenAI calls with unknown cost only considers turns that reached a terminal state more than one minute ago, so in-flight provider settlement can finish first and is not overwritten.

Code: `backend/services/chat_openai_budget_service.py::ChatOpenAIBudgetService.mark_stale_dispatched_unknown`

## Starlette's disconnect probe swallows a cancellation

Starlette's request.is_disconnected uses a local AnyIO cancellation scope, so the first cancellation delivered while it polls is absorbed and it returns False. MCP gateway code must not rely on cancelling a disconnect poll to stop a completed call.

Code: `backend/tests/chat_gateway/test_pwc_mcp.py::test_completed_call_does_not_wait_for_disconnect_poll_that_swallows_cancel`

## Stream close persists interruption as a last resort

Starlette may close an async response generator with GeneratorExit rather than delivering CancelledError. The stream's close path therefore persists the interruption itself, so a disconnected browser cannot leave the turn generating until its lease expires.

Code: `backend/services/chat_stream_service.py::ChatStreamOrchestrator._close`

## Synthetic probe pauses instead of paging when credentials are missing

An unconfigured synthetic monitor account is not a chat outage. The probe records a credential_unavailable pause and delivers pending alerts but does not page.

Code: `backend/scripts/run_chat_synthetic_probe.py::main`

## Title budget trips stickily only when no reservation can return headroom

In-flight title reservations may settle below their conservative bounds. The title budget circuit becomes sticky-tripped only when spend has reached the cap or no reservations are outstanding; otherwise a cap-exceeding request is rejected without tripping.

Code: `backend/services/chat_title_budget_service.py::ChatTitleBudgetService.reserve_call`

## Tool starts without an intervening result share a round

Pre-tool hooks fire before the streamed assistant-message boundary that registers the complete tool batch. Tool starts with no result between them are therefore parallel calls from one assistant turn and are counted as a single tool round for the round limit.

Code: `backend/services/chat_agent_service.py::SearchCallLimiter.register_call`

## Trace export failures warn instead of paging

Langfuse/Trackio export failures lose observability, not chat turns. They raise warnings rather than pages and never force the paid synthetic probe.

Code: `backend/services/chat_operational_alert_service.py::TELEMETRY_ALERT_NAMES`

## Trackio export errors log only the exception class

Export payloads contain chat traces and the request carries the HF token. Errors are logged only by exception class or HTTP status, never with payloads, response bodies or exception messages that could include them.

Code: `backend/services/chat_trackio_service.py::TrackioClient._send`

## Trackio export never follows redirects

Trackio export requests carry the HF token as a bearer credential, so the client disables redirect following to keep credentials on the configured Space URL.

Code: `backend/services/chat_trackio_service.py::TrackioClient._send`

## Trackio exporter thread never dies on errors

The Trackio exporter runs on a background thread. Any unexpected exception is logged and the batch counted as failed, so telemetry failures never stop the exporter or affect chat.

Code: `backend/services/chat_trackio_service.py::TrackioClient._work`

## Trackio trace IDs match the Langfuse scheme

Trackio trace IDs use the same deterministic derivation as Langfuse (first 32 hex chars of SHA-256 of the seed), and the value is stored in a persisted database column. Changing the derivation breaks correlation between stored rows and traces.

Code: `backend/services/chat_trackio_service.py::TrackioClient.create_trace_id`

## Turn ledger follows raised spend caps only

An existing turn reservation ledger adopts a higher application spend cap after a reviewed raise; any other change to the limit, including a decrease, is rejected as an error.

Code: `backend/services/chat_turn_admission.py::ChatTurnAdmissionService.initialize`

## Uploaded file tokens are bounded separately from request bytes

Files attached by OpenAI file_id are not in the request body, so request_bytes cannot bound them. OpenAIRequestBounds carries an upload-time token estimate (file_input_tokens) that budget checks add to the byte-based estimate.

Code: `backend/services/chat_openai_budget_service.py::OpenAIRequestBounds`

/**
 * Wire types for the chat API: the SSE stream protocol, persisted sessions,
 * shares, model discovery, and billing/usage status.
 */

/* ---------- Chat stream protocol (`POST /chat/stream`) ---------- */

export type ReasoningEffort = "low" | "medium" | "high" | "max";

/** Structured metadata for one search hit.
 * Keys are always present; unavailable values are null / empty lists. */
export interface ChatPaperMetadata {
  arxiv_id: string | null;
  source: "arxiv" | "external";
  source_url: string | null;
  /** Backend-hosted or paper-supplied preview image. */
  thumbnail_url: string | null;
  authors: { name: string }[];
  /** ISO date, e.g. "2025-02-18". */
  published: string | null;
  /** Display name, e.g. "CVPR 2024". */
  conference: string | null;
  citation_count: number | null;
  tasks: { name: string; slug: string }[];
  methods: { name: string; slug: string }[];
  repositories: { url: string; stars: number | null }[];
  project_pages: { url: string }[];
}

/** One paper returned by the assistant's `search_papers` tool. */
export interface ChatPaperHit {
  /** Citation/route key: arXiv ID or internal numeric ID (`/paper/<route_id>`). */
  route_id: string;
  title: string;
  /** Bounded abstract or external-resource description (≤4,000 chars). */
  content: string;
  content_truncated: boolean;
  metadata: ChatPaperMetadata;
}

export interface ChatCitation {
  kind?: "catalog_paper" | "external_source" | "paper" | "web";
  route_id: string | null;
  url?: string | null;
  source_type?: "paper" | "article" | null;
  provider?: "paperswithcode" | "semantic_scholar" | "web";
  title: string;
  excerpt?: string | null;
  source_url: string | null;
  thumbnail_url?: string | null;
  favicon_url?: string | null;
  arxiv_id?: string | null;
  semantic_scholar_id?: string | null;
  authors?: string[];
  published?: string | null;
  conference?: string | null;
  citation_count?: number | null;
}

export type ChatEvent =
  | {
      type: "stream_start";
      request_id: string;
      session_id: string | null;
      provider_execution?: boolean;
    }
  | { type: "workspace_ready" }
  | { type: "compaction_status"; state: "started" | "finished" }
  | {
      type: "lifecycle";
      phase: "preparing_workspace" | "starting_agent" | "connecting_model";
    }
  | { type: "reasoning_start" }
  | { type: "reasoning_delta"; text: string }
  | { type: "reasoning_end" }
  | { type: "tool_call"; id: string; name: string; args: Record<string, unknown> }
  | {
      type: "tool_call_start";
      id: string;
      name: string;
      content_index: number;
      redacted?: boolean;
    }
  | {
      type: "tool_call_arguments_delta";
      id: string;
      name: string;
      delta: string;
      partial_args: Record<string, unknown>;
      snapshot?: boolean;
      redacted?: boolean;
    }
  | {
      type: "tool_call_arguments_done";
      id: string;
      name: string;
      args: Record<string, unknown>;
      redacted?: boolean;
    }
  | {
      type: "app_start";
      id: string;
      instance_id: string;
      provider: "excalidraw";
      server: "excalidraw";
      tool: "create_view";
      resource_uri: "ui://excalidraw/mcp-app.html";
      input: { elements: string };
    }
  | {
      type: "app_result";
      id: string;
      status: "ready" | "error";
      took_ms: number;
      result: McpAppResult;
    }
  | {
      type: "tool_result";
      id: string;
      took_ms: number;
      status?: "success" | "error" | "denied";
      content?: { type: "text"; text: string; truncated: boolean }[];
      metadata?: { exit_code: number | null; output_truncated: boolean };
      /** Legacy local_mcp result shape. */
      hits?: number;
      results?: ChatPaperHit[];
    }
  | {
      type: "artifact_start";
      publication_id: string;
      identifier: string;
      kind: "posterly";
      title: string;
    }
  | {
      type: "artifact_ready";
      publication_id: string;
      artifact_id: string;
      version_id: string;
      identifier: string;
      version: number;
      kind: "posterly";
      title: string;
      preview_mime: "image/png";
      source_language: "html";
      gate_status: "passed" | "warnings" | "failed";
      total_bytes: number;
    }
  | { type: "artifact_error"; publication_id: string; code: string; message: string }
  | PaperArtifactEvent
  | { type: "sandbox_start"; session_id: string }
  | { type: "sandbox_ready"; session_id: string; cold_start_ms: number }
  | { type: "answer_delta"; text: string }
  | { type: "done"; followups?: string[]; finish_reason?: string; citations?: ChatCitation[] }
  | { type: "error"; message: string; code?: string }
  | { type: "session_title_start" }
  | { type: "session_title_delta"; text: string }
  | { type: "session_title_done"; title: string };

export interface ChatStreamRequest {
  message: string;
  session_id: string | null;
  client_message_id: string;
  initial_model?: string;
  replace_message_id?: string;
  retry_message_id?: string;
  prior_revision?: number;
  paper_mentions?: PaperMentionWire[];
  web_search_enabled: boolean;
  reasoning_effort?: ReasoningEffort;
  primary_paper_route_id?: string;
  viewer_context?: { page: number };
  paper_selection?: PaperSelectionWire;
}

export interface PaperMentionDraft {
  key: string;
  route_id: string;
  title: string;
  source: "arxiv" | "external";
  start: number;
  end: number;
  unavailable?: boolean;
}

export type PaperMentionWire = Pick<PaperMentionDraft, "route_id" | "title" | "start" | "end">;

export interface PaperSelectionWire {
  route_id: string;
  paper_version: string;
  page: number;
  text: string;
}

/* ---------- Persisted display blocks ---------- */

export interface ReasoningBlock {
  kind: "reasoning";
  text: string;
  /** True while reasoning tokens are still streaming in. */
  active: boolean;
  open: boolean;
  citations?: ChatCitation[];
}

export interface ToolBlock {
  kind: "tool";
  schema_version?: 1 | 2;
  id: string;
  name: string;
  args: Record<string, unknown>;
  argumentText?: string;
  argumentState?: "streaming" | "done";
  arguments_redacted?: boolean;
  status: "running" | "done" | "success" | "error" | "denied";
  content?: { type: "text"; text: string; truncated: boolean }[];
  metadata?: { exit_code: number | null; output_truncated: boolean };
  /** Legacy local_mcp projection fields. */
  hits?: number;
  took_ms?: number;
  results?: ChatPaperHit[];
  open: boolean;
}

export interface McpAppResult {
  content: { type: "text"; text: string; truncated: boolean }[];
  structuredContent: { checkpointId?: string };
  isError: boolean;
}

export interface AppBlock {
  kind: "app";
  schema_version: 1;
  instance_id: string;
  provider: "excalidraw";
  server: "excalidraw";
  tool: "create_view";
  resource_uri: "ui://excalidraw/mcp-app.html";
  resource_version?: string | null;
  status: "loading" | "ready" | "error" | "unavailable" | "incompatible";
  input: { elements: string };
  result: McpAppResult;
  csp: Record<string, string[]>;
  permissions: { clipboardWrite?: boolean };
  height: number;
  public_fork?: boolean;
}

export interface AnswerBlock {
  kind: "answer";
  text: string;
  done: boolean;
  citations?: ChatCitation[];
}

export interface ArtifactBlock {
  kind: "artifact";
  schema_version: 1;
  scope: "owner" | "public";
  publication_id?: string;
  artifact_id?: string;
  version_id?: string;
  public_capability?: string;
  identifier: string;
  version?: number;
  artifact_kind: "posterly" | "latex_paper";
  title: string;
  status: "generating" | "ready" | "error";
  phase?: "preparing_paper" | "designing_poster" | "checking_poster" | "rendering_poster" | "publishing_poster";
  preview_mime?: "image/png" | "application/pdf";
  source_language?: "html" | "latex";
  gate_status?: "passed" | "warnings" | "failed";
  total_bytes?: number;
  error_code?: string;
  error_message?: string;
}

export interface PaperArtifactEvent {
  type: "paper_artifact";
  operation: "create" | "begin-edit" | "draft" | "repair";
  activated: boolean;
  descriptor: LatexPaperArtifactDescriptor;
}

export type ChatBlock = ReasoningBlock | ToolBlock | AppBlock | ArtifactBlock | AnswerBlock;

export interface ChatBrowserLatencyUpdate {
  submission_to_stream_start_ms?: number;
  submission_to_first_visible_delta_ms?: number;
  submission_to_first_reasoning_delta_ms?: number;
  submission_to_first_tool_call_ms?: number;
  submission_to_first_answer_delta_ms?: number;
  terminal_classification?:
    | "complete"
    | "stopped"
    | "error"
    | "network_error"
    | "aborted";
}

/* ---------- Sessions, shares, and models ---------- */

export interface ChatSession {
  id: string;
  title: string;
  selected_model: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  is_busy: boolean;
  web_search_enabled: boolean;
  reasoning_effort?: ReasoningEffort;
  primary_paper?: {
    id: string;
    route_id: string;
    title: string;
    arxiv_id: string | null;
  } | null;
}

export interface ChatSessionDetail extends ChatSession {
  transcript_status: string;
  latex_paper?: LatexPaperArtifactDescriptor | null;
  messages: Array<{
    id: string;
    turn_id: string;
    sequence: number;
    role: "user" | "assistant";
    content: string;
    paper_mentions?: Array<Omit<PaperMentionDraft, "key"> & { occurrence_id: string }>;
    paper_selection?: {
      route_id: string;
      paper_version: string;
      page: number;
      text: string;
      text_sha256?: string;
      included_bytes?: number;
      page_verified?: boolean;
    } | null;
    viewer_context?: { page: number } | null;
    revision: number;
    status: string;
    display_blocks: ChatBlock[];
    citations: ChatCitation[];
    followups: string[];
    finish_reason?: string | null;
    error_code: string | null;
    reasoning_effort?: ReasoningEffort;
  }>;
}

export interface LatexPaperVersionDescriptor {
  version_id: string;
  version: number;
  source_digest: string;
  compile_status: "queued" | "compiling" | "succeeded" | "failed";
  created_at?: string | null;
  actor_type?: "ai" | "human" | "restore";
  parent_version_id?: string | null;
  preview_head_version_id?: string | null;
  compile_diagnostics?: Array<{
    severity: "error" | "warning";
    phase?: string | null;
    file?: string | null;
    line?: number | null;
    message: string;
  }>;
  repair_attempts_remaining?: number;
  repair_exhausted?: boolean;
  generation_provenance?: Record<string, unknown> | null;
  display_metadata: {
    summary?: string | null;
    unresolved_todo_count: number;
    warning_count: number;
  };
  provenance?: {
    action: "human_save" | "ai_draft" | "ai_repair" | "restore";
    model_identity?: string | null;
    change_summary?: string | null;
    changed_files: string[];
    reference_changes: string[];
    restored_from_version_id?: string | null;
  };
}

export interface LatexPaperHistoryPage {
  items: LatexPaperVersionDescriptor[];
  next_cursor?: string | null;
}

export interface LatexPaperArtifactDescriptor {
  artifact_id: string;
  title: string;
  source_head?: LatexPaperVersionDescriptor | null;
  preview_head?: LatexPaperVersionDescriptor | null;
  editing_enabled?: boolean;
}

/** Files of one LaTeX paper version. */
export interface LatexPaperManifest {
  root_document: string;
  files: Array<{ path: string; media_type: string }>;
}

/** One published version of a Posterly poster. */
export interface PosterVersionSummary {
  version_id: string;
  version: number;
  gate_status: ArtifactBlock["gate_status"];
  total_bytes: number;
}

export interface PosterManifest {
  entrypoint: string;
  gate_report: string;
  downloads: Array<{ path: string; label: string }>;
  source_files?: string[];
  canvas: { width: number; height: number; unit: string; orientation: string };
  direction: string;
  gate_summary: string[];
}

export interface ChatShareSummary {
  share_id: string;
  public_path: string;
  created_at: string;
  updated_at: string;
}

export interface PublicChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  paper_mentions?: Array<Omit<PaperMentionDraft, "key"> & { occurrence_id: string }>;
  paper_selection?: {
    route_id: string;
    paper_version: string;
    page: number;
    text: string;
    text_sha256?: string;
    included_bytes?: number;
    page_verified?: boolean;
  } | null;
  display_blocks: ChatBlock[];
  citations: ChatCitation[];
  model?: string | null;
  display_state: "complete" | "interrupted" | "failed";
  finish_reason: string | null;
  error: string | null;
}

export type ChatModelProvider = "huggingface" | "openrouter" | "openai";

export interface ChatShareDetail {
  share_id: string;
  created_at: string;
  updated_at: string;
  model: string | null;
  model_label: string | null;
  model_provider: ChatModelProvider | null;
  messages: PublicChatMessage[];
}

export interface ChatModelChoice {
  id: string;
  label: string;
  provider: ChatModelProvider;
  // Billed to the Papers With Code organization, so no user authorization.
  sponsored?: boolean;
  reasoning_efforts?: ReasoningEffort[];
}

export interface InferenceBillingStatus {
  connected: boolean;
  account_type: string | null;
  monthly_credits_usd: number | null;
  pay_as_you_go: boolean;
  usage_url: string;
  token_url: string;
  bill_to: string | null;
  organizations: Array<{ name: string; display_name: string }>;
}

export interface OpenRouterUsageStatus {
  used_percent: number;
  remaining_percent: number;
  resets_at: string;
  available: boolean;
  unavailable_reason: "personal_allowance_exhausted" | "workspace_limit_exhausted" | "shared_credits_exhausted" | "provider_status_unavailable" | "staging_funding_disabled" | null;
  production_chat_url?: string;
  as_of: string;
}

export interface OpenAIUsageStatus {
  used_percent: number;
  remaining_percent: number;
  resets_at: string;
  available: boolean;
  as_of: string;
}

export interface OpenRouterCredentialStatus {
  connected: boolean;
  verified_at: string | null;
  fallback_enabled: boolean;
}


export interface ChatAvailability {
  status: 'available' | 'paused';
  reason: 'chat_temporarily_disabled' | null;
  expected_recovery_at: string | null;
  paper_mentions_enabled: boolean;
  web_search_available: boolean;
  native_pdf_reader_enabled?: boolean;
  paper_reader_chat_enabled?: boolean;
  paper_reader_selection_enabled?: boolean;
  paper_reader_citations_enabled?: boolean;
  paper_artifacts_enabled?: boolean;
}

export interface ChatAutocompleteVocabulary {
  names: string[];
}

export interface ChatSandboxSpendStatus {
  environment: string;
  provider_mode: 'starter_workspace' | 'team_environments';
  billing_cycle: string;
  cycle_end_at: string;
  circuit_state: 'armed' | 'warning' | 'tripped';
  trip_reason: string | null;
  tripped_at: string | null;
  estimated_microusd: number;
  provider_floor_microusd: number;
  effective_microusd: number;
  warning_microusd: number;
  application_cap_microusd: number;
  environment_cap_microusd: number | null;
  workspace_cap_microusd: number;
  remaining_microusd: number;
  reconciliation_state: 'fresh' | 'stale' | 'unavailable';
  last_metered_at: string | null;
  last_reconciled_at: string | null;
  last_reconciliation_attempt_at: string | null;
  next_reconciliation_at: string | null;
  live_count: number;
  termination_uncertain_count: number;
  live_states: Record<'starting' | 'blank' | 'busy' | 'idle' | 'draining' | 'termination_uncertain', number>;
  burn_rate_microusd_per_hour: number | null;
  projected_cap_hit_at: string | null;
  prior_cycle: {
    billing_cycle: string;
    estimated_microusd: number;
    provider_floor_microusd: number;
    effective_microusd: number;
  } | null;
  daily_spend: Array<{ date: string; blank_pool_microusd: number; assigned_microusd: number }>;
  events: Array<{ id: string; type: string; severity: string; reason: string | null; created_at: string; details: Record<string, unknown> }>;
}

export interface ChatWebSearchBudgetStatus {
  environment: string;
  billing_cycle: string;
  cycle_end_at: string;
  available: boolean;
  warning_calls: number;
  hard_limit_calls: number;
  call_count: number;
  remaining_calls: number;
  success_count: number;
  failure_count: number;
  provider_cost_microusd: number;
  last_latency_ms: number | null;
  last_result_count: number | null;
  circuit_state: 'armed' | 'warning' | 'cooldown' | 'tripped';
  trip_reason: string | null;
  cooldown_until: string | null;
  last_provider_error_class: string | null;
  events: Array<{
    id: string;
    type: string;
    error_class: string | null;
    created_at: string;
    details: Record<string, unknown>;
  }>;
}

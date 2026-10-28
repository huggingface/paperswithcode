/**
 * Streaming client for the AI research assistant (`/chat`).
 *
 * The chat UI consumes a flat stream of `ChatEvent`s describing one assistant
 * turn: reasoning tokens, `search_papers` tool calls with their results, and
 * final answer tokens. This is the exact event vocabulary the FastAPI SSE
 * endpoint (`POST /api/v1/chat/stream`, `text/event-stream`) emits — each
 * SSE message carries one JSON-encoded `ChatEvent` in its `data:` field.
 *
 * Builds without `VITE_CHAT_LIVE=1` replay a scripted mock stream instead
 * (see `chatMock.ts`), so the chat UI can be exercised without a live backend.
 *
 * Answer text protocol: answer deltas concatenate into GitHub-flavored Markdown,
 * with inline paper citations of the form `[label](paper:<route_id>)`.
 * Citations become links only after the backend returns an authoritative
 * per-block citation snapshot. Legacy search-result metadata remains supported
 * for historical sessions (see `ChatMarkdown.tsx`).
 *
 * Wire contract: hits carry bounded `content` plus a structured `metadata`
 * dict, are keyed by `route_id` (arXiv ID for arXiv papers, internal numeric
 * ID for external resources), and deliberately carry no relevance score until
 * a calibrated reranker exists.
 */

import { chatApi } from "@/lib/api/chat";
import { notifyStaleAuth } from "@/lib/apiAuth";
import { ApiError } from "@/lib/apiTransport";
import { mockChatStream } from "@/lib/chatMock";

export type ReasoningEffort = "low" | "medium" | "high" | "max";

/** Every chat runs at this effort; the picker is no longer user-facing. */
export const DEFAULT_REASONING_EFFORT: ReasoningEffort = "medium";

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

type PaperMentionWire = Pick<PaperMentionDraft, "route_id" | "title" | "start" | "end">;

export interface PaperSelectionDraft {
  routeId: string;
  paperVersion: string;
  page: number;
  text: string;
}

export interface PaperSelectionWire {
  route_id: string;
  paper_version: string;
  page: number;
  text: string;
}

export interface ChatDraft {
  text: string;
  paperMentions: PaperMentionDraft[];
  paperSelection?: PaperSelectionDraft;
}

/* ---------- UI message model (also persisted for session history) ---------- */

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

interface McpAppResult {
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

interface PaperArtifactEvent {
  type: "paper_artifact";
  operation: "create" | "begin-edit" | "draft" | "repair";
  activated: boolean;
  descriptor: import("./chatSessions").LatexPaperArtifactDescriptor;
}

export type ChatBlock = ReasoningBlock | ToolBlock | AppBlock | ArtifactBlock | AnswerBlock;

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  /** User messages: the raw question. */
  text?: string;
  /** Assistant messages: ordered stream blocks. */
  blocks?: ChatBlock[];
  streaming?: boolean;
  compacting?: boolean;
  followups?: string[];
  /** From the `done` event; anything other than "success" is surfaced. */
  finishReason?: string;
  citations?: ChatCitation[];
  error?: string;
  errorCode?: string;
  revision?: number;
  status?: string;
  paperMentions?: PaperMentionDraft[];
  paperSelection?: PaperSelectionDraft;
}

export const isChatLive = (): boolean => {
  const raw = import.meta.env.VITE_CHAT_LIVE;
  if (!raw) return false;
  const lowered = String(raw).trim().toLowerCase();
  return lowered === "1" || lowered === "true" || lowered === "yes";
};

/** Smooth streaming is the live-chat default; false-like values are a rollback switch. */
export const isChatSmoothStreamingEnabled = (): boolean => {
  const raw = import.meta.env.VITE_CHAT_SMOOTH_STREAMING;
  if (raw === undefined || raw === null || String(raw).trim() === "") return true;
  return !["0", "false", "off", "no"].includes(String(raw).trim().toLowerCase());
};

export interface StreamChatOptions {
  signal?: AbortSignal;
  afterSequence?: number;
  onSequence?: (sequence: number) => void;
}

type ParsedSSEFrame = {
  sequence: number | null;
  event: string;
  data: string;
};

export class ChatStreamError extends Error {
  constructor(
    message: string,
    public readonly code?: string,
    public readonly status?: number,
    public readonly retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = "ChatStreamError";
  }
}

export class ChatTransportError extends Error {
  constructor(message = "The assistant stream was interrupted.") {
    super(message);
    this.name = "ChatTransportError";
  }
}

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

/**
 * Best-effort staging telemetry. A rejected report must never affect the chat
 * stream or surface an error to the user.
 */
export function reportChatLatency(
  requestId: string,
  update: ChatBrowserLatencyUpdate,
): void {
  if (!isChatLive()) return;
  try {
    void chatApi.reportLatency(requestId, update).catch(() => undefined);
  } catch {
    // Telemetry must never affect the chat.
  }
}

/**
 * Stream one assistant turn for the given conversation history (ending with
 * the newest user message). Yields `ChatEvent`s until `done` or `error`.
 */
export function streamChat(
  request: ChatStreamRequest,
  opts: StreamChatOptions = {},
): AsyncGenerator<ChatEvent> {
  if (!isChatLive()) {
    return mockChatStream(request.message, opts.signal);
  }
  return streamChatOverSSE(request, opts);
}

/** Reattach to a durable turn after navigation or a full page reload. */
export function resumeChat(
  sessionId: string,
  opts: StreamChatOptions = {},
): AsyncGenerator<ChatEvent> {
  return resumeChatOverSSE(sessionId, opts);
}

/**
 * Real transport: POST the history, parse the `text/event-stream` response.
 * `EventSource` can't POST a body, so we read the stream off `fetch` directly.
 */
async function* streamChatOverSSE(
  request: ChatStreamRequest,
  opts: StreamChatOptions,
): AsyncGenerator<ChatEvent> {
  try {
    const res = await chatApi.stream(request, opts.signal);
    yield* readChatSSE(res, opts);
  } catch (error) {
    throw classifyStreamFailure(error);
  }
}

async function* resumeChatOverSSE(
  sessionId: string,
  opts: StreamChatOptions,
): AsyncGenerator<ChatEvent> {
  try {
    const res = await chatApi.resumeStream(sessionId, opts.signal, opts.afterSequence);
    yield* readChatSSE(res, opts);
  } catch (error) {
    throw classifyStreamFailure(error);
  }
}

function classifyStreamFailure(error: unknown): Error {
  if (error instanceof ChatStreamError || error instanceof ChatTransportError) return error;
  if (error instanceof SyntaxError) {
    return new ChatStreamError(
      "The assistant returned an invalid stream event.",
      "invalid_stream_event",
    );
  }
  return new ChatTransportError(
    error instanceof Error ? error.message : "The assistant stream was interrupted.",
  );
}

function parseSSEFrame(raw: string): ParsedSSEFrame {
  let sequence: number | null = null;
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("id:")) {
      const rawSequence = line.slice(3).trim();
      if (/^[1-9]\d*$/.test(rawSequence)) sequence = Number(rawSequence);
    } else if (line.startsWith("event:")) {
      event = line.slice(6).trimStart();
    } else if (line.startsWith("data:")) {
      data.push(line.slice(5).trimStart());
    }
  }
  return { sequence, event, data: data.join("\n") };
}

async function* readChatSSE(
  res: Response,
  opts: StreamChatOptions,
): AsyncGenerator<ChatEvent> {
  if (!res.ok || !res.body) {
    const apiError = !res.ok ? new ApiError(res, await res.text()) : null;
    if (apiError) notifyStaleAuth(apiError);
    const detail = apiError?.detail;
    const structuredDetail = typeof detail === "object" && detail !== null ? detail : null;
    const stagingDenied = res.status === 403 && !detail;
    const rawRetryAfter = Number(res.headers.get("Retry-After"));
    const retryAfterSeconds = Number.isFinite(rawRetryAfter) && rawRetryAfter >= 0
      ? Math.min(300, Math.ceil(rawRetryAfter))
      : undefined;
    throw new ChatStreamError(
      stagingDenied
        ? "Chat on staging is limited to approved Hugging Face users. Sign in with an approved account and try again."
        : apiError?.message || `Chat stream failed (${res.status})`,
      structuredDetail && "code" in structuredDetail && typeof structuredDetail.code === "string"
        ? structuredDetail.code
        : stagingDenied ? "staging_access_required" : undefined,
      res.status,
      retryAfterSeconds,
    );
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let latestSequence = opts.afterSequence && opts.afterSequence > 0
    ? opts.afterSequence
    : 0;

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE messages are separated by a blank line; each may span multiple
      // `data:` lines that concatenate into one JSON payload.
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const frame = parseSSEFrame(raw);
        if (!frame.data || frame.data === "[DONE]") continue;
        if (frame.sequence !== null && frame.sequence <= latestSequence) continue;
        const event = JSON.parse(frame.data) as ChatEvent;
        if (frame.sequence !== null) {
          latestSequence = frame.sequence;
          opts.onSequence?.(frame.sequence);
        }
        yield event;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

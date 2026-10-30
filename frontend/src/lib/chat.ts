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
import type {
  ChatBlock,
  ChatBrowserLatencyUpdate,
  ChatCitation,
  ChatEvent,
  ChatPaperHit,
  ChatStreamRequest,
  PaperMentionDraft,
  ReasoningEffort,
} from "@/lib/api/chat.types";

// Wire types live with the API client; existing imports keep using this module.
export type * from "@/lib/api/chat.types";

/** Every chat runs at this effort; the picker is no longer user-facing. */
export const DEFAULT_REASONING_EFFORT: ReasoningEffort = "medium";

export interface PaperSelectionDraft {
  routeId: string;
  paperVersion: string;
  page: number;
  text: string;
}

export interface ChatDraft {
  text: string;
  paperMentions: PaperMentionDraft[];
  paperSelection?: PaperSelectionDraft;
}

/* ---------- UI message model (also persisted for session history) ---------- */

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

/** The newest user prompt in a transcript. */
export function latestUserMessage(messages: readonly ChatMessage[]): ChatMessage | undefined {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === "user") return messages[index];
  }
  return undefined;
}

/** The composer draft that reproduces a sent prompt. */
export function draftFromMessage(message: ChatMessage | undefined): ChatDraft {
  return {
    text: message?.text ?? "",
    paperMentions: message?.paperMentions ?? [],
    ...(message?.paperSelection ? { paperSelection: message.paperSelection } : {}),
  };
}

/** Every paper returned by search tools in a transcript, keyed by route ID. */
export function collectChatPapers(messages: readonly ChatMessage[]): Record<string, ChatPaperHit> {
  const papers: Record<string, ChatPaperHit> = {};
  for (const message of messages) {
    for (const block of message.blocks ?? []) {
      if (block.kind === "tool") {
        for (const result of block.results ?? []) papers[result.route_id] = result;
      }
    }
  }
  return papers;
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

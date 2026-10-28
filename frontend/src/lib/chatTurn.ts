import { type ChatDraft, type ChatEvent, type ChatMessage, type ChatStreamRequest, type ReasoningEffort, ChatStreamError } from "./chat";
import { chatLifecycleReducer, initialChatLifecycle, type ChatLifecycleAction } from "./chatLifecycle";

export interface ChatTurnConfiguration {
  model?: string;
  webSearchEnabled: boolean;
  reasoningEffort: ReasoningEffort;
}

export interface EditRequest {
  targetId: string;
  snapshot: ChatMessage[];
}

export interface PendingGeneration {
  question: string;
  draft: ChatDraft;
  request: ChatStreamRequest;
  optimistic: ChatMessage[];
  original: ChatMessage[];
  edit?: EditRequest;
  retryAt: number;
  retryAfterSeconds: number;
}

const PROVIDER_ERRORS = new Set([
  "openrouter_monthly_budget_exhausted", "openrouter_unavailable",
  "openrouter_byok_credential_invalid", "openrouter_byok_billing_error",
  "openrouter_byok_rate_limit", "hf_inference_billing_exhausted",
]);
const DRAFT_ERRORS = new Set([
  "paper_context_unavailable", "paper_mention_unavailable", "paper_mentions_disabled",
  "paper_selection_disabled", "paper_selection_requires_reader", "paper_selection_paper_mismatch",
  "paper_selection_version_mismatch", "paper_selection_page_invalid", "paper_selection_too_large",
  "chat_storage_quota_exceeded",
]);

/** Owns the active turn, independently of the conversation currently on screen.
 * Presentation snapshots must never be fed back into this state during streaming.
 */
export class ChatTurn {
  configuration: ChatTurnConfiguration | undefined;
  private lifecycle = initialChatLifecycle();
  private _busy = false;
  private _pendingCapacity: PendingGeneration | null = null;
  private _sawStreamStart = false;
  private _providerExecuted = false;
  private _providerStatusChanged = false;
  private terminal: "pending" | "complete" | "error" | "transport_error" | "already_complete" = "pending";
  private rejection: "disabled" | "capacity" | "draft" | null = null;

  get busy() { return this._busy; }
  get pendingCapacity() { return this._pendingCapacity; }
  get sawStreamStart() { return this._sawStreamStart; }
  get sawTerminalEvent() { return this.terminal === "complete" || this.terminal === "error"; }
  get streamFailed() { return this.terminal === "error" || this.terminal === "transport_error"; }
  get admissionRejected() { return this.rejection !== null; }
  get shouldRefreshProvider() {
    return (this._sawStreamStart && this._providerExecuted) || this._providerStatusChanged;
  }
  finish() { this._busy = false; }
  queueCapacity(pending: PendingGeneration) { this._pendingCapacity = pending; }
  cancelCapacity() { this._pendingCapacity = null; }

  projectSession(sessionId: string | null) {
    return this._busy && sessionId === this.sessionId ? this.messages : null;
  }

  get state() { return this.lifecycle; }
  get messages() { return this.lifecycle.messages; }
  get sessionId() { return this.lifecycle.sessionId; }

  transition(action: ChatLifecycleAction) {
    this.lifecycle = chatLifecycleReducer(this.lifecycle, action);
    return this.lifecycle;
  }

  start(messages: ChatMessage[], sessionId: string | null, configuration?: ChatTurnConfiguration) {
    this.configuration = configuration;
    this._busy = true;
    this._sawStreamStart = this._providerExecuted = this._providerStatusChanged = false;
    this.terminal = "pending";
    this.rejection = null;
    this.transition({ type: "start", messages, sessionId });
  }

  restore(messages: ChatMessage[], sessionId = this.sessionId) {
    return this.transition({ type: "load", messages, sessionId });
  }

  observe(event: ChatEvent) {
    if (event.type === "stream_start") {
      this._sawStreamStart = true;
      this._providerExecuted = event.provider_execution !== false;
    }
    if (event.type === "done" || event.type === "error") {
      this.terminal = event.type === "done" ? "complete" : "error";
    }
    if (event.type === "error" && PROVIDER_ERRORS.has(event.code ?? "")) {
      this._providerStatusChanged = true;
      return true;
    }
    return false;
  }

  reject(error: unknown, resumed: boolean) {
    const code = error instanceof ChatStreamError ? error.code : undefined;
    const kind = resumed && code === "chat_not_busy" ? "completed"
      : code === "chat_temporarily_disabled" ? "disabled"
      : code === "chat_capacity" ? "capacity"
      : DRAFT_ERRORS.has(code ?? "") ? "draft"
      : PROVIDER_ERRORS.has(code ?? "") ? "provider" : "network";
    this.terminal = kind === "completed" ? "already_complete" : "transport_error";
    this.rejection = kind === "disabled" || kind === "capacity" || kind === "draft" ? kind : null;
    this._providerStatusChanged ||= kind === "provider";
    return kind;
  }

  reset() {
    this._busy = false;
    this._pendingCapacity = null;
    this.transition({ type: "reset" });
  }
}

import { type ChatDraft, type ChatEvent, type ChatMessage, type ChatStreamRequest, type ReasoningEffort, ChatStreamError } from "./chat";
import { chatErrorClass } from "./chatErrors";
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

/** How a turn ended, as far as the browser observed it. */
export type ChatTurnTerminal =
  | "pending"
  /** `done` event. */
  | "complete"
  /** `error` event. */
  | "error"
  /** The request or stream failed in transport. */
  | "transport_error"
  /** The backend refused admission (disabled, capacity, or an invalid draft). */
  | "admission_rejected"
  /** A reconnect found the turn had already settled. */
  | "already_complete";

interface ChatTurnProgress {
  /** Set by `stream_start`; replays without provider work report `providerExecuted: false`. */
  streamStart: { providerExecuted: boolean } | null;
  providerStatusChanged: boolean;
  terminal: ChatTurnTerminal;
}

/** The single model of a turn's status. */
export type ChatTurnPhase =
  | { status: "idle" }
  | ({ status: "streaming" } & ChatTurnProgress)
  /** Finished streaming; the outcome stays readable until the next turn starts. */
  | ({ status: "settled" } & ChatTurnProgress);

export type ChatRejection = "completed" | "disabled" | "capacity" | "draft" | "provider" | "network";

/** What the selected conversation shows; React reads it through `useSyncExternalStore`. */
export interface ChatTurnSnapshot {
  messages: ChatMessage[];
  busy: boolean;
  sessionError: string;
  capacityRequest: PendingGeneration | null;
  disabledRequest: { question: string; draft: ChatDraft } | null;
}

type ChatView = Pick<ChatTurnSnapshot, "messages" | "sessionError" | "disabledRequest">;

/** Owns the active turn, independently of the conversation currently on screen,
 * plus the transcript that conversation shows. The shown transcript is either a
 * projection of this turn or a loaded transcript; presentation snapshots must
 * never be fed back into the turn state during streaming.
 */
export class ChatTurn {
  configuration: ChatTurnConfiguration | undefined;
  private lifecycle = initialChatLifecycle();
  private _phase: ChatTurnPhase = { status: "idle" };
  private _pendingCapacity: PendingGeneration | null = null;
  private view: ChatView = { messages: [], sessionError: "", disabledRequest: null };
  private snapshot: ChatTurnSnapshot = this.buildSnapshot();
  private readonly listeners = new Set<() => void>();

  /* ---------- External store ---------- */

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  getSnapshot = () => this.snapshot;

  private buildSnapshot(): ChatTurnSnapshot {
    return { ...this.view, busy: this.busy, capacityRequest: this._pendingCapacity };
  }

  private publish() {
    const next = this.buildSnapshot();
    const previous = this.snapshot;
    if ((Object.keys(next) as (keyof ChatTurnSnapshot)[]).every((key) => next[key] === previous[key])) return;
    this.snapshot = next;
    for (const listener of this.listeners) listener();
  }

  /** The transcript the selected conversation shows. */
  get visibleMessages() { return this.view.messages; }

  /** Change what the selected conversation shows in one update. */
  present(update: Partial<ChatView>) {
    this.view = { ...this.view, ...update };
    this.publish();
  }

  /* ---------- Turn status ---------- */

  get phase() { return this._phase; }
  get busy() { return this._phase.status === "streaming"; }
  get pendingCapacity() { return this._pendingCapacity; }
  get sawStreamStart() { return this._phase.status !== "idle" && this._phase.streamStart !== null; }
  get sawTerminalEvent() {
    return this._phase.status !== "idle"
      && (this._phase.terminal === "complete" || this._phase.terminal === "error");
  }
  get streamFailed() {
    return this._phase.status !== "idle" && (
      this._phase.terminal === "error"
      || this._phase.terminal === "transport_error"
      || this._phase.terminal === "admission_rejected"
    );
  }
  get admissionRejected() {
    return this._phase.status !== "idle" && this._phase.terminal === "admission_rejected";
  }
  get shouldRefreshProvider() {
    if (this._phase.status === "idle") return false;
    return Boolean(this._phase.streamStart?.providerExecuted) || this._phase.providerStatusChanged;
  }

  private progress(update: Partial<ChatTurnProgress>) {
    if (this._phase.status !== "idle") this._phase = { ...this._phase, ...update };
  }

  finish() {
    if (this._phase.status === "streaming") this._phase = { ...this._phase, status: "settled" };
    this.publish();
  }

  queueCapacity(pending: PendingGeneration) {
    this._pendingCapacity = pending;
    this.publish();
  }

  cancelCapacity() {
    this._pendingCapacity = null;
    this.publish();
  }

  /* ---------- Turn projection ---------- */

  projectSession(sessionId: string | null) {
    return this.busy && sessionId === this.sessionId ? this.messages : null;
  }

  get state() { return this.lifecycle; }
  get messages() { return this.lifecycle.messages; }
  get sessionId() { return this.lifecycle.sessionId; }

  /** Advance the turn; `project` also shows the result in the selected conversation. */
  transition(action: ChatLifecycleAction, project = false) {
    this.lifecycle = chatLifecycleReducer(this.lifecycle, action);
    if (project) this.view = { ...this.view, messages: this.lifecycle.messages };
    this.publish();
    return this.lifecycle;
  }

  /** Begin a turn and show its optimistic transcript. */
  start(messages: ChatMessage[], sessionId: string | null, configuration?: ChatTurnConfiguration) {
    this.configuration = configuration;
    this._phase = { status: "streaming", streamStart: null, providerStatusChanged: false, terminal: "pending" };
    this.view = { ...this.view, messages, sessionError: "" };
    this.transition({ type: "start", messages, sessionId });
  }

  /** Replace the turn's transcript; `show` also shows it, and `view` updates
   * the selected conversation in the same notification. */
  restore(
    messages: ChatMessage[],
    { sessionId = this.sessionId, show = false, view }: {
      sessionId?: string | null;
      show?: boolean;
      view?: Partial<Omit<ChatView, "messages">>;
    } = {},
  ) {
    this.lifecycle = chatLifecycleReducer(this.lifecycle, { type: "load", messages, sessionId });
    this.view = { ...this.view, ...(show ? { messages } : {}), ...view };
    this.publish();
    return this.lifecycle;
  }

  /** Record what an event says about the turn. Returns true when a provider
   * error should hand the draft back to the composer. */
  observe(event: ChatEvent) {
    if (event.type === "stream_start") {
      this.progress({ streamStart: { providerExecuted: event.provider_execution !== false } });
    }
    if (event.type === "done" || event.type === "error") {
      this.progress({ terminal: event.type === "done" ? "complete" : "error" });
    }
    if (event.type === "error" && chatErrorClass(event.code) === "provider") {
      this.progress({ providerStatusChanged: true });
      return true;
    }
    return false;
  }

  reject(error: unknown, resumed: boolean): ChatRejection {
    const code = error instanceof ChatStreamError ? error.code : undefined;
    const errorClass = chatErrorClass(code);
    const kind: ChatRejection = resumed && code === "chat_not_busy" ? "completed"
      : code === "chat_temporarily_disabled" ? "disabled"
      : code === "chat_capacity" ? "capacity"
      : errorClass === "draft" ? "draft"
      : errorClass === "provider" ? "provider" : "network";
    this.progress({
      terminal: kind === "completed" ? "already_complete"
        : kind === "disabled" || kind === "capacity" || kind === "draft" ? "admission_rejected"
        : "transport_error",
      ...(kind === "provider" ? { providerStatusChanged: true } : {}),
    });
    return kind;
  }

  /** Forget the turn and clear the selected conversation. */
  reset() {
    this._phase = { status: "idle" };
    this._pendingCapacity = null;
    this.view = { ...this.view, messages: [], sessionError: "" };
    this.transition({ type: "reset" });
  }
}

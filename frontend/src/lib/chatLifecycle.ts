import type { ChatBlock, ChatEvent, ChatMessage } from "./chat";

const WORKSPACE_STATUS = "Preparing research workspace…";
const LIFECYCLE_STATUS = {
  preparing_workspace: "Preparing secure workspace…",
  starting_agent: "Starting research agent…",
  connecting_model: "Connecting to model…",
} as const;

/** The visible projection of one turn. Turn status lives in `ChatTurn.phase`. */
export interface ChatLifecycleState {
  messages: ChatMessage[];
  sessionId: string | null;
  title: string;
}

/** How the stream loop treats each event, besides reducing it into messages. */
export interface ChatEventTraits {
  /** Smooth streaming: deltas coalesce into frames, structural events flush them. */
  presentation: "delta" | "structural" | "silent";
  /** The delayed "Preparing research workspace…" status. */
  workspaceStatus: "arm" | "clear" | null;
  /** Terminal events close the turn's browser latency record. */
  terminal: "complete" | "error" | null;
}

const traits = (
  presentation: ChatEventTraits["presentation"],
  workspaceStatus: ChatEventTraits["workspaceStatus"] = null,
  terminal: ChatEventTraits["terminal"] = null,
): ChatEventTraits => ({ presentation, workspaceStatus, terminal });

export const EVENT_TRAITS: Readonly<Record<ChatEvent["type"], ChatEventTraits>> = {
  stream_start: traits("silent"),
  sandbox_start: traits("silent", "arm"),
  sandbox_ready: traits("silent", "clear"),
  workspace_ready: traits("silent", "clear"),
  lifecycle: traits("structural", "clear"),
  compaction_status: traits("structural"),
  session_title_start: traits("silent"),
  session_title_delta: traits("silent"),
  session_title_done: traits("silent"),
  reasoning_start: traits("structural", "clear"),
  reasoning_delta: traits("delta", "clear"),
  reasoning_end: traits("structural"),
  tool_call: traits("structural", "clear"),
  tool_call_start: traits("structural", "clear"),
  tool_call_arguments_delta: traits("delta", "clear"),
  tool_call_arguments_done: traits("structural", "clear"),
  tool_result: traits("structural"),
  app_start: traits("structural", "clear"),
  app_result: traits("structural", "clear"),
  artifact_start: traits("structural", "clear"),
  artifact_ready: traits("structural", "clear"),
  artifact_error: traits("structural", "clear"),
  paper_artifact: traits("structural"),
  answer_delta: traits("delta", "clear"),
  done: traits("structural", "clear", "complete"),
  error: traits("structural", "clear", "error"),
};

export type ChatLifecycleAction =
  | { type: "start"; messages: ChatMessage[]; sessionId: string | null }
  | { type: "event"; event: ChatEvent }
  | { type: "load"; messages: ChatMessage[]; sessionId: string | null }
  | { type: "workspace_status" }
  | { type: "clear_workspace_status" }
  | { type: "settle" }
  | { type: "stop" }
  | { type: "toggle_block"; messageId: string; blockIndex: number }
  | { type: "reset" };

export const initialChatLifecycle = (): ChatLifecycleState => ({
  messages: [],
  sessionId: null,
  title: "",
});

export function findLastMatchingIndex<T>(
  items: readonly T[],
  predicate: (item: T) => boolean,
): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (predicate(items[index])) return index;
  }
  return -1;
}

function withoutWorkspaceStatus(message: ChatMessage): ChatMessage {
  if (
    message.status !== WORKSPACE_STATUS
    && !Object.values(LIFECYCLE_STATUS).includes(
      message.status as (typeof LIFECYCLE_STATUS)[keyof typeof LIFECYCLE_STATUS],
    )
  ) return message;
  const { status: _status, ...rest } = message;
  return rest;
}

function patchLast(
  messages: ChatMessage[],
  patch: (message: ChatMessage) => ChatMessage,
): ChatMessage[] {
  if (!messages.length) return messages;
  const next = messages.slice();
  next[next.length - 1] = patch(next[next.length - 1]);
  return next;
}

function patchBlock(
  messages: ChatMessage[],
  match: (block: ChatBlock, index: number, blocks: ChatBlock[]) => boolean,
  patch: (block: ChatBlock) => ChatBlock,
): ChatMessage[] {
  return patchLast(messages, (message) => {
    const visible = withoutWorkspaceStatus(message);
    const blocks = visible.blocks ?? [];
    return {
      ...visible,
      blocks: blocks.map((block, index) => (
        match(block, index, blocks) ? patch(block) : block
      )),
    };
  });
}

function reduceEvent(
  state: ChatLifecycleState,
  event: ChatEvent,
): ChatLifecycleState {
  switch (event.type) {
    case "stream_start":
      return event.session_id ? { ...state, sessionId: event.session_id } : state;
    case "sandbox_start":
    case "sandbox_ready":
    case "workspace_ready":
      return state;
    case "lifecycle":
      return {
        ...state,
        messages: patchLast(state.messages, (message) => (
          message.role === "assistant"
          && message.streaming
          && (message.blocks?.length ?? 0) === 0
            ? { ...message, status: LIFECYCLE_STATUS[event.phase] }
            : message
        )),
      };
    case "session_title_start":
      return { ...state, title: "" };
    case "session_title_delta":
      return {
        ...state,
        title: `${state.title}${event.text}`.replace(/\s+/g, " ").slice(0, 80),
      };
    case "session_title_done":
      return { ...state, title: event.title };
    case "compaction_status":
      return { ...state, messages: patchLast(state.messages, (message) => ({
        ...message, compacting: Boolean(message.streaming && event.state === "started"),
      })) };
    case "reasoning_start":
      return {
        ...state,
        messages: patchLast(state.messages, (message) => {
          const visible = withoutWorkspaceStatus(message);
          return {
            ...visible,
            blocks: [
              ...(visible.blocks ?? []).map((block) => (
                block.kind === "reasoning" && block.active
                  ? { ...block, active: false, open: false }
                  : block
              )),
              { kind: "reasoning", text: "", active: true, open: true },
            ],
          };
        }),
      };
    case "reasoning_delta":
      return {
        ...state,
        messages: patchBlock(
          state.messages,
          (block, index, blocks) => block.kind === "reasoning"
            && findLastMatchingIndex(blocks, (candidate) => candidate.kind === "reasoning") === index,
          (block) => block.kind === "reasoning"
            ? { ...block, text: block.text + event.text }
            : block,
        ),
      };
    case "reasoning_end":
      return {
        ...state,
        messages: patchLast(state.messages, (message) => {
          const blocks = message.blocks ?? [];
          const currentIndex = findLastMatchingIndex(
            blocks,
            (block) => block.kind === "reasoning" && block.active,
          );
          if (currentIndex < 0) return message;
          const current = blocks[currentIndex];
          if (current.kind !== "reasoning") return message;
          const previous = blocks[currentIndex - 1];
          if (previous?.kind === "reasoning" && previous.text === current.text) {
            return { ...message, blocks: blocks.filter((_block, index) => index !== currentIndex) };
          }
          return {
            ...message,
            blocks: blocks.map((block, index) => index === currentIndex
              ? { ...current, active: false, open: false }
              : block),
          };
        }),
      };
    case "tool_call":
      return {
        ...state,
        messages: patchLast(state.messages, (message) => {
          const visible = withoutWorkspaceStatus(message);
          return {
            ...visible,
            blocks: [...(visible.blocks ?? []), {
              kind: "tool",
              id: event.id,
              name: event.name,
              args: event.args,
              status: "running",
              open: false,
            }],
          };
        }),
      };
    case "tool_call_start":
      return {
        ...state,
        messages: patchLast(state.messages, (message) => {
          const visible = withoutWorkspaceStatus(message);
          return {
            ...visible,
            blocks: [...(visible.blocks ?? []), {
              kind: "tool",
              schema_version: 2,
              id: event.id,
              name: event.name,
              args: {},
              argumentText: "",
              argumentState: "streaming",
              arguments_redacted: event.redacted,
              status: "running",
              open: false,
            }],
          };
        }),
      };
    case "tool_call_arguments_delta":
      return {
        ...state,
        messages: patchBlock(
          state.messages,
          (block) => block.kind === "tool" && block.id === event.id,
          (block) => block.kind === "tool" ? {
            ...block,
            args: event.partial_args,
            argumentText: event.snapshot
              ? event.delta
              : `${block.argumentText ?? ""}${event.delta}`,
            arguments_redacted: block.arguments_redacted || event.redacted,
          } : block,
        ),
      };
    case "tool_call_arguments_done":
      return {
        ...state,
        messages: patchBlock(
          state.messages,
          (block) => block.kind === "tool" && block.id === event.id,
          (block) => block.kind === "tool" ? {
            ...block,
            args: event.args,
            argumentText: JSON.stringify(event.args),
            argumentState: "done",
            arguments_redacted: block.arguments_redacted || event.redacted,
          } : block,
        ),
      };
    case "app_start":
      return {
        ...state,
        messages: patchLast(state.messages, (message) => {
          const visible = withoutWorkspaceStatus(message);
          return { ...visible, blocks: [...(visible.blocks ?? []), {
            kind: "app", schema_version: 1, instance_id: event.instance_id,
            provider: event.provider, server: event.server, tool: event.tool,
            resource_uri: event.resource_uri, status: "loading", input: event.input,
            result: { content: [], structuredContent: {}, isError: false },
            csp: {}, permissions: { clipboardWrite: true }, height: 525,
          }] };
        }),
      };
    case "app_result":
      return {
        ...state,
        messages: patchBlock(
          state.messages,
          (block) => block.kind === "app" && block.instance_id === event.id,
          (block) => block.kind === "app" ? { ...block, status: event.status, result: event.result } : block,
        ),
      };
    case "tool_result":
      return {
        ...state,
        messages: patchBlock(
          state.messages,
          (block) => block.kind === "tool" && block.id === event.id,
          (block) => block.kind !== "tool"
            ? block
            : event.status
              ? {
                  ...block,
                  schema_version: 2,
                  status: event.status,
                  took_ms: event.took_ms,
                  content: event.content,
                  metadata: event.metadata,
                  open: event.status !== "success",
                }
              : {
                  ...block,
                  status: "done",
                  hits: event.hits,
                  took_ms: event.took_ms,
                  results: event.results,
                },
        ),
      };
    case "artifact_start":
      return {
        ...state,
        messages: patchLast(state.messages, (message) => {
          const visible = withoutWorkspaceStatus(message);
          return { ...visible, blocks: [...(visible.blocks ?? []), {
            kind: "artifact", schema_version: 1, scope: "owner",
            publication_id: event.publication_id, identifier: event.identifier,
            artifact_kind: "posterly", title: event.title, status: "generating",
            phase: "publishing_poster",
          }] };
        }),
      };
    case "artifact_ready":
      return {
        ...state,
        messages: patchBlock(
          state.messages,
          (block) => block.kind === "artifact" && block.publication_id === event.publication_id,
          (block) => block.kind === "artifact" ? {
            ...block, artifact_id: event.artifact_id, version_id: event.version_id,
            identifier: event.identifier, version: event.version, title: event.title,
            status: "ready", preview_mime: event.preview_mime,
            source_language: event.source_language, gate_status: event.gate_status,
            total_bytes: event.total_bytes, phase: undefined,
          } : block,
        ),
      };
    case "artifact_error":
      return {
        ...state,
        messages: patchBlock(
          state.messages,
          (block) => block.kind === "artifact" && block.publication_id === event.publication_id,
          (block) => block.kind === "artifact" ? {
            ...block, status: "error", phase: undefined,
            error_code: event.code, error_message: event.message,
          } : block,
        ),
      };
    case "answer_delta":
      return {
        ...state,
        messages: patchLast(state.messages, (message) => {
          const visible = withoutWorkspaceStatus(message);
          const blocks = visible.blocks ?? [];
          const last = blocks.at(-1);
          if (last?.kind === "answer" && !last.done) {
            return {
              ...visible,
              blocks: [...blocks.slice(0, -1), { ...last, text: last.text + event.text }],
            };
          }
          return {
            ...visible,
            blocks: [...blocks, { kind: "answer", text: event.text, done: false }],
          };
        }),
      };
    case "done":
      return {
        ...state,
        messages: patchLast(state.messages, (message) => ({
          ...message,
          streaming: false,
          compacting: false,
          followups: event.followups,
          finishReason: event.finish_reason,
          citations: event.citations,
          blocks: (message.blocks ?? []).map((block) => (
            block.kind === "answer"
              ? { ...block, done: true }
              : block.kind === "reasoning" && block.active
                ? { ...block, active: false, open: false }
                : block
          )),
        })),
      };
    case "error":
      return {
        ...state,
        messages: patchLast(state.messages, (message) => ({
          ...message,
          streaming: false,
          compacting: false,
          error: event.message,
          errorCode: event.code,
          blocks: (message.blocks ?? []).map((block) => (
            block.kind === "reasoning" && block.active
              ? { ...block, active: false, open: false }
              : block.kind === "tool" && block.status === "running"
                ? { ...block, status: "error", open: true }
              : block
          )),
        })),
      };
    default:
      return state;
  }
}

function stopMessages(messages: ChatMessage[]): ChatMessage[] {
  return patchLast(messages, (message) => {
    if (message.role !== "assistant") return message;
    const blocks = (message.blocks ?? []).flatMap((block): ChatBlock[] => {
      if (block.kind === "tool" && block.status === "running") {
        return [{ ...block, status: "error", open: true }];
      }
      if (block.kind === "reasoning" && block.active) {
        return block.text ? [{ ...block, active: false, open: false }] : [];
      }
      if (block.kind === "answer") return [{ ...block, done: true }];
      return [block];
    });
    return { ...message, blocks, streaming: false, compacting: false, finishReason: "stopped" };
  });
}

export function chatLifecycleReducer(
  state: ChatLifecycleState,
  action: ChatLifecycleAction,
): ChatLifecycleState {
  switch (action.type) {
    case "start":
      return {
        messages: action.messages,
        sessionId: action.sessionId,
        title: "",
      };
    case "event":
      return reduceEvent(state, action.event);
    case "load":
      return {
        messages: action.messages,
        sessionId: action.sessionId,
        title: state.title,
      };
    case "workspace_status":
      return {
        ...state,
        messages: patchLast(state.messages, (message) => (
          message.role === "assistant"
          && message.streaming
          && (message.blocks?.length ?? 0) === 0
          && !message.error
            ? { ...message, status: WORKSPACE_STATUS }
            : message
        )),
      };
    case "clear_workspace_status":
      return { ...state, messages: patchLast(state.messages, withoutWorkspaceStatus) };
    case "settle":
      return {
        ...state,
        messages: patchLast(state.messages, (message) => (
          message.streaming ? { ...message, streaming: false, compacting: false } : message
        )),
      };
    case "stop":
      return { ...state, messages: stopMessages(state.messages) };
    case "toggle_block":
      return { ...state, messages: toggleChatBlock(state.messages, action.messageId, action.blockIndex) };
    case "reset":
      return initialChatLifecycle();
  }
}

export function toggleChatBlock(messages: ChatMessage[], messageId: string, blockIndex: number) {
  return messages.map((message) => message.id !== messageId ? message : {
    ...message,
    blocks: message.blocks?.map((block, index) => (
      index === blockIndex && (block.kind === "reasoning" || block.kind === "tool")
        ? { ...block, open: !block.open } : block
    )),
  });
}

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  type ChatEvent,
  type ChatMessage,
  type ChatStreamRequest,
  ChatStreamError,
  ChatTransportError,
} from "@/lib/chat";
import type { ChatSessionDetail } from "@/lib/chatSessions";
import { useChat } from "@/hooks/useChat";

const { streamChatMock, resumeChatMock, getSessionMock, reportChatLatencyMock } = vi.hoisted(() => ({
  streamChatMock: vi.fn(),
  resumeChatMock: vi.fn(),
  getSessionMock: vi.fn(),
  reportChatLatencyMock: vi.fn(),
}));

vi.mock("@/lib/chat", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/chat")>();
  return {
    ...actual,
    streamChat: streamChatMock,
    resumeChat: resumeChatMock,
    reportChatLatency: reportChatLatencyMock,
  };
});

vi.mock("@/lib/chatSessions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/chatSessions")>();
  return { ...actual, getSession: getSessionMock };
});

const sessionDetail = (
  id: string,
  messages: ChatSessionDetail["messages"],
): ChatSessionDetail => ({
  id,
  title: "Original title",
  selected_model: "zai-org/GLM-5.2",
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
  message_count: messages.length,
  is_busy: false,
  web_search_enabled: false,
  transcript_status: "ready",
  messages,
});

const persistedUser = (
  id: string,
  sequence: number,
  content: string,
  revision = 1,
): ChatSessionDetail["messages"][number] => ({
  id,
  turn_id: `${id}-turn`,
  sequence,
  role: "user",
  content,
  revision,
  status: "complete",
  display_blocks: [],
  citations: [],
  followups: [],
  error_code: null,
});

const persistedAssistant = (
  id: string,
  sequence: number,
  content: string,
): ChatSessionDetail["messages"][number] => ({
  id,
  turn_id: `${id}-turn`,
  sequence,
  role: "assistant",
  content,
  revision: 1,
  status: "complete",
  display_blocks: [{ kind: "answer", text: content, done: true }],
  citations: [],
  followups: [],
  error_code: null,
});

const uiTurn = (id: string, text: string): ChatMessage[] => [
  { id, role: "user", text, revision: 1, status: "complete" },
  {
    id: `${id}-answer`,
    role: "assistant",
    blocks: [{ kind: "answer", text: `Answer to ${text}`, done: true }],
  },
];

const stream = (...events: ChatEvent[]) => async function* () {
  for (const event of events) yield event;
};

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
};

const flushMicrotasks = async () => {
  await act(async () => {
    for (let index = 0; index < 12; index += 1) await Promise.resolve();
  });
};

const renderChat = (
  sessionId: string | null = "session-1",
  webSearchEnabled = false,
  paperRoute?: string,
) => {
  const onSessionId = vi.fn();
  const onSettled = vi.fn();
  const onInterrupted = vi.fn();
  const result = renderHook(() => useChat({
    sessionId,
    initialModel: "zai-org/GLM-5.2",
    webSearchEnabled,
    ...(paperRoute ? { primaryPaperRouteId: paperRoute, reasoningEffort: "max" as const } : {}),
    onSessionId,
    onTitle: vi.fn(),
    onSettled,
    onInterrupted,
  }));
  return { ...result, onSessionId, onSettled, onInterrupted };
};

beforeEach(() => {
  streamChatMock.mockReset();
  resumeChatMock.mockReset();
  getSessionMock.mockReset();
  reportChatLatencyMock.mockReset();
});

describe("useChat reload recovery", () => {
  it("replays and follows an active turn after the session is reloaded", async () => {
    resumeChatMock.mockImplementation(() => stream(
      { type: "stream_start", request_id: "r-active", session_id: "session-1" },
      { type: "reasoning_start" },
      { type: "reasoning_delta", text: "Checking the evidence" },
      { type: "reasoning_end" },
      { type: "answer_delta", text: "Recovered answer" },
      { type: "done", finish_reason: "success" },
    )());
    getSessionMock.mockResolvedValue(sessionDetail("session-1", [
      persistedUser("user-active", 1, "Active question"),
      persistedAssistant("assistant-active", 2, "Recovered answer"),
    ]));
    const restored = [{
      ...uiTurn("user-active", "Active question")[0],
      status: "generating",
    }];
    const { result } = renderChat();

    act(() => result.current.load(restored, "session-1", true));

    expect(result.current.busy).toBe(true);
    expect(result.current.messages.at(-1)).toMatchObject({
      role: "assistant",
      streaming: true,
    });
    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(resumeChatMock).toHaveBeenCalledWith("session-1", expect.any(Object));
    expect(result.current.messages.at(-1)).toMatchObject({
      role: "assistant",
      blocks: [{ kind: "answer", text: "Recovered answer", done: true }],
    });
  });

  it("does not show an error when the turn completes before reconnect", async () => {
    const canonical = deferred<ChatSessionDetail>();
    resumeChatMock.mockImplementation(() => (async function* () {
      yield* stream()();
      throw new ChatStreamError(
        "This chat is not generating.",
        "chat_not_busy",
        409,
      );
    })());
    getSessionMock.mockReturnValue(canonical.promise);
    const restored = [{
      ...uiTurn("user-completed", "Question completed while disconnected")[0],
      status: "generating",
    }];
    const { result } = renderChat();

    act(() => result.current.load(restored, "session-1", true));
    await flushMicrotasks();

    expect(result.current.busy).toBe(false);
    expect(result.current.messages.at(-1)).toMatchObject({
      role: "assistant",
      streaming: true,
    });
    expect(result.current.messages.at(-1)?.error).toBeUndefined();

    canonical.resolve(sessionDetail("session-1", [
      persistedUser("user-completed", 1, "Question completed while disconnected"),
      persistedAssistant("assistant-completed", 2, "Persisted completed answer"),
    ]));
    await waitFor(() => expect(result.current.messages.at(-1)).toMatchObject({
      role: "assistant",
      blocks: [{ kind: "answer", text: "Persisted completed answer", done: true }],
    }));
  });
});

describe("useChat transport recovery", () => {
  it("resumes the same turn from the latest cursor without posting again", async () => {
    vi.useFakeTimers();
    const postedClientMessageIds: string[] = [];
    streamChatMock.mockImplementation((request: ChatStreamRequest, opts: {
      onSequence?: (sequence: number) => void;
    }) => {
      postedClientMessageIds.push(request.client_message_id);
      return (async function* () {
        opts.onSequence?.(11);
        yield { type: "stream_start", request_id: "r1", session_id: "session-1" } as ChatEvent;
        opts.onSequence?.(12);
        yield { type: "answer_delta", text: "Part one. " } as ChatEvent;
        throw new ChatTransportError("connection reset");
      })();
    });
    resumeChatMock.mockImplementation(() => stream(
      { type: "answer_delta", text: "Part two." },
      { type: "done", finish_reason: "success" },
    )());
    getSessionMock.mockRejectedValue(new Error("not persisted yet"));
    const { result } = renderChat();

    act(() => expect(result.current.send("Continue this turn")).toBe(true));
    await flushMicrotasks();
    expect(resumeChatMock).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    await flushMicrotasks();
    expect(result.current.busy).toBe(false);

    expect(resumeChatMock).toHaveBeenCalledWith("session-1", expect.objectContaining({
      afterSequence: 12,
      signal: expect.any(Object),
    }));
    expect(postedClientMessageIds).toHaveLength(1);
    expect(streamChatMock).toHaveBeenCalledTimes(1);
    expect(result.current.messages.at(-1)?.blocks).toEqual([
      { kind: "answer", text: "Part one. Part two.", done: true, citations: undefined },
    ]);
  });

  it("uses bounded reconnect delays and exposes the failed turn after exhaustion", async () => {
    vi.useFakeTimers();
    streamChatMock.mockImplementation((_request: ChatStreamRequest, opts: {
      onSequence?: (sequence: number) => void;
    }) => (async function* () {
      opts.onSequence?.(7);
      yield { type: "stream_start", request_id: "r1", session_id: "session-1" } as ChatEvent;
      throw new ChatTransportError("connection reset");
    })());
    resumeChatMock.mockImplementation(() => (async function* () {
      yield* stream()();
      throw new ChatTransportError("still offline");
    })());
    getSessionMock.mockRejectedValue(new Error("not persisted yet"));
    const { result } = renderChat();

    act(() => expect(result.current.send("Keep trying")).toBe(true));
    await flushMicrotasks();
    await act(async () => { await vi.advanceTimersByTimeAsync(249); });
    expect(resumeChatMock).toHaveBeenCalledTimes(0);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(resumeChatMock).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(499); });
    expect(resumeChatMock).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(resumeChatMock).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(999); });
    expect(resumeChatMock).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    await flushMicrotasks();
    expect(result.current.busy).toBe(false);

    expect(resumeChatMock).toHaveBeenCalledTimes(3);
    expect(streamChatMock).toHaveBeenCalledTimes(1);
    expect(result.current.messages.at(-1)).toMatchObject({
      role: "assistant",
      error: "still offline",
    });
  });

  it.each([
    ["terminal event", async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: "session-1" } as ChatEvent;
      yield { type: "error", code: "provider_error", message: "Provider rejected the turn" } as ChatEvent;
    }],
    ["typed stream error", async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: "session-1" } as ChatEvent;
      throw new ChatStreamError("Request rejected", "request_rejected", 400);
    }],
  ])("does not reconnect after a %s", async (_label, source) => {
    vi.useFakeTimers();
    streamChatMock.mockImplementation(source);
    getSessionMock.mockRejectedValue(new Error("not persisted yet"));
    const { result } = renderChat();

    act(() => expect(result.current.send("Do not retry")).toBe(true));
    await flushMicrotasks();
    expect(result.current.busy).toBe(false);

    expect(resumeChatMock).not.toHaveBeenCalled();
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useChat billing failures", () => {
  it("submits explicit immutable web-search authorization", async () => {
    streamChatMock.mockImplementation(() => stream(
      { type: "stream_start", request_id: "r1", session_id: "session-1" },
      { type: "done", finish_reason: "success" },
    )());
    getSessionMock.mockRejectedValue(new Error("not persisted yet"));
    const { result } = renderChat("session-1", true);

    act(() => result.current.send("Find current evidence"));
    await waitFor(() => expect(result.current.busy).toBe(false));

    expect(streamChatMock).toHaveBeenCalledWith(
      expect.objectContaining({ web_search_enabled: true }),
      expect.any(Object),
    );
  });

  it("preserves the billing error code for an actionable message", async () => {
    streamChatMock.mockImplementation(() => stream(
      { type: "stream_start", request_id: "r1", session_id: "session-1" },
      {
        type: "error",
        code: "hf_inference_billing_exhausted",
        message: "Review pay-as-you-go billing.",
      },
    )());
    getSessionMock.mockRejectedValue(new Error("not persisted yet"));
    const { result } = renderChat();

    act(() => result.current.send("What changed?"));

    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(result.current.messages.at(-1)).toMatchObject({
      role: "assistant",
      error: "Review pay-as-you-go billing.",
      errorCode: "hf_inference_billing_exhausted",
    });
  });
});

describe("useChat durable capacity handling", () => {
  it("restores the complete draft when paper hydration fails before admission", async () => {
    streamChatMock.mockImplementation(() => (async function* () {
      yield* stream()();
      throw new ChatStreamError(
        "Attached paper context could not be prepared.",
        "paper_context_unavailable",
        503,
      );
    })());
    const original = uiTurn("user-1", "Earlier");
    const draft = {
      text: "Read @Attention Is All You Need",
      paperMentions: [{
        key: "mention-1",
        route_id: "1706.03762",
        title: "Attention Is All You Need",
        source: "arxiv" as const,
        start: 5,
        end: 31,
      }],
    };
    const { result, onInterrupted } = renderChat();
    act(() => result.current.load(original));
    act(() => expect(result.current.send(draft)).toBe(true));

    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(result.current.messages).toEqual(original);
    expect(result.current.sessionError).toBe("Attached paper context could not be prepared.");
    expect(onInterrupted).toHaveBeenCalledWith(draft);
  });

  it("sends a typed paper selection and restores it after a selection admission error", async () => {
    let request: ChatStreamRequest | undefined;
    streamChatMock.mockImplementation((next: ChatStreamRequest) => {
      request = next;
      return (async function* () {
        yield* stream()();
        throw new ChatStreamError(
          "Paper selection is currently disabled. Remove it before sending.",
          "paper_selection_disabled",
          409,
        );
      })();
    });
    const original = uiTurn("user-1", "Earlier");
    const draft = {
      text: "What does this mean?",
      paperMentions: [],
      paperSelection: {
        routeId: "2608.09119",
        paperVersion: "v1",
        page: 4,
        text: "quoted evidence",
      },
    };
    const { result, onInterrupted } = renderChat();
    act(() => result.current.load(original));
    act(() => expect(result.current.send(draft)).toBe(true));
    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(request?.paper_selection).toEqual({
      route_id: "2608.09119",
      paper_version: "v1",
      page: 4,
      text: "quoted evidence",
    });
    expect(result.current.messages).toEqual(original);
    expect(onInterrupted).toHaveBeenCalledWith(draft);
  });

  it("preserves the draft without a timed retry when chat is disabled", async () => {
    streamChatMock.mockImplementation(() => (async function* () {
      yield* stream()();
      throw new ChatStreamError(
        "Chat is temporarily disabled",
        "chat_temporarily_disabled",
        503,
      );
    })());
    const original = uiTurn("user-1", "Earlier");
    const { result } = renderChat();
    act(() => result.current.load(original));
    act(() => expect(result.current.send("Keep this draft")).toBe(true));
    await waitFor(() => expect(result.current.disabledRequest).not.toBeNull());
    expect(result.current.disabledRequest?.question).toBe("Keep this draft");
    expect(result.current.capacityRequest).toBeNull();
    expect(result.current.messages).toEqual(original);
  });

  it("uses the same popup state for a brand-new chat", async () => {
    let request: ChatStreamRequest | undefined;
    streamChatMock.mockImplementation((next: ChatStreamRequest) => {
      request = next;
      return (async function* () {
        yield* stream()();
        throw new ChatStreamError("At capacity", "chat_capacity", 429, 0);
      })();
    });
    const { result } = renderChat(null);

    act(() => expect(result.current.send("Start research")).toBe(true));
    await waitFor(() => expect(result.current.capacityRequest).not.toBeNull());

    expect(request).toMatchObject({
      message: "Start research",
      session_id: null,
      initial_model: "zai-org/GLM-5.2",
    });
    expect(result.current.messages).toEqual([]);
  });

  it("restores the draft state and retries with the exact request metadata", async () => {
    const requests: ChatStreamRequest[] = [];
    streamChatMock
      .mockImplementationOnce((request: ChatStreamRequest) => {
        requests.push(request);
        return (async function* () {
          yield* stream()();
          throw new ChatStreamError("At capacity", "chat_capacity", 429, 0);
        })();
      })
      .mockImplementationOnce((request: ChatStreamRequest) => {
        requests.push(request);
        return stream(
          { type: "stream_start", request_id: "r2", session_id: "session-1" },
          { type: "done", finish_reason: "success" },
        )();
      });
    getSessionMock.mockResolvedValue(sessionDetail("session-1", [
      persistedUser("user-1", 1, "Earlier"),
      persistedAssistant("answer-1", 2, "Earlier answer"),
      persistedUser("user-2", 3, "Follow up"),
      persistedAssistant("answer-2", 4, "Follow-up answer"),
    ]));
    const original = uiTurn("user-1", "Earlier");
    const { result } = renderChat();
    act(() => result.current.load(original));

    const mention = {
      key: "mention-1",
      route_id: "1706.03762",
      title: "Attention Is All You Need",
      source: "arxiv" as const,
      start: 10,
      end: 36,
    };
    act(() => expect(result.current.send({
      text: "Follow up @Attention Is All You Need",
      paperMentions: [mention],
    })).toBe(true));
    await waitFor(() => expect(result.current.capacityRequest).not.toBeNull());

    expect(result.current.messages).toEqual(original);
    expect(result.current.capacityRequest?.question).toBe("Follow up @Attention Is All You Need");
    act(() => expect(result.current.retryCapacity()).toBe(true));
    await waitFor(() => expect(result.current.busy).toBe(false));

    expect(requests).toHaveLength(2);
    expect(requests[1]).toEqual(requests[0]);
    expect(requests[1].client_message_id).toBe(requests[0].client_message_id);
    expect(requests[1].paper_mentions).toEqual([{
      route_id: mention.route_id,
      title: mention.title,
      start: mention.start,
      end: mention.end,
    }]);
  });

  it("preserves edit-and-retry metadata and cancel performs no new request", async () => {
    let request: ChatStreamRequest | undefined;
    streamChatMock.mockImplementation((next: ChatStreamRequest) => {
      request = next;
      return (async function* () {
        yield* stream()();
        throw new ChatStreamError("At capacity", "chat_capacity", 429, 0);
      })();
    });
    const original = [...uiTurn("user-1", "First"), ...uiTurn("user-2", "Second")];
    const { result } = renderChat();
    act(() => result.current.load(original));

    act(() => expect(result.current.editAndResend("user-2", "Edited second")).toBe(true));
    await waitFor(() => expect(result.current.capacityRequest).not.toBeNull());

    expect(request).toMatchObject({
      message: "Edited second",
      session_id: "session-1",
      replace_message_id: "user-2",
      prior_revision: 1,
    });
    expect(result.current.messages).toEqual(original);
    act(() => result.current.cancelCapacity());
    expect(result.current.capacityRequest).toBeNull();
    expect(streamChatMock).toHaveBeenCalledTimes(1);
  });

  it("preserves failed-turn retry metadata", async () => {
    let request: ChatStreamRequest | undefined;
    streamChatMock.mockImplementation((next: ChatStreamRequest) => {
      request = next;
      return (async function* () {
        yield* stream()();
        throw new ChatStreamError("At capacity", "chat_capacity", 429, 0);
      })();
    });
    const failed: ChatMessage[] = [
      { id: "failed-user", role: "user", text: "Retry me", revision: 2, status: "error" },
      { id: "failed-answer", role: "assistant", error: "Provider failed" },
    ];
    const { result } = renderChat();
    act(() => result.current.load(failed));

    act(() => expect(result.current.send("Retry me")).toBe(true));
    await waitFor(() => expect(result.current.capacityRequest).not.toBeNull());

    expect(request).toMatchObject({
      session_id: "session-1",
      replace_message_id: "failed-user",
      prior_revision: 2,
    });
    expect(result.current.messages).toEqual(failed);
  });
});

describe("useChat reasoning projection", () => {
  it("collapses consecutive identical completed reasoning blocks", async () => {
    streamChatMock.mockImplementation(() => stream(
      { type: "stream_start", request_id: "r1", session_id: "session-1" },
      { type: "reasoning_start" },
      { type: "reasoning_delta", text: "**Same plan**" },
      { type: "reasoning_end" },
      { type: "reasoning_start" },
      { type: "reasoning_delta", text: "**Same plan**" },
      { type: "reasoning_end" },
      { type: "done", followups: [], finish_reason: "success" },
    )());
    const { result } = renderChat();

    act(() => result.current.send("What changed?"));

    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(result.current.messages.at(-1)?.blocks).toEqual([{
      kind: "reasoning",
      text: "**Same plan**",
      active: false,
      open: false,
    }]);
  });

  it("keeps Luna reasoning blocks sequential across delayed boundaries", async () => {
    streamChatMock.mockImplementation(() => stream(
      { type: "stream_start", request_id: "r1", session_id: "session-1" },
      { type: "reasoning_start" },
      { type: "reasoning_delta", text: "First plan" },
      { type: "reasoning_start" },
      { type: "reasoning_delta", text: "Second plan" },
      { type: "tool_call", id: "tool-1", name: "Bash", args: {} },
      { type: "reasoning_end" },
      { type: "done", followups: [], finish_reason: "success" },
    )());
    const { result } = renderChat();

    act(() => result.current.send("What changed?"));

    await waitFor(() => expect(result.current.busy).toBe(false));
    const reasoning = result.current.messages.at(-1)?.blocks?.filter(
      (block) => block.kind === "reasoning",
    );
    expect(reasoning).toEqual([
      { kind: "reasoning", text: "First plan", active: false, open: false },
      { kind: "reasoning", text: "Second plan", active: false, open: false },
    ]);
  });
});

describe("useChat editAndResend", () => {
  it("edits the first prompt in place, including unchanged text", async () => {
    let request: ChatStreamRequest | undefined;
    streamChatMock.mockImplementation((next: ChatStreamRequest) => {
      request = next;
      return stream(
        { type: "stream_start", request_id: "r1", session_id: "session-1" },
        { type: "done", followups: [], finish_reason: "success" },
      )();
    });
    getSessionMock.mockResolvedValue(sessionDetail("session-1", [
      persistedUser("new-user", 1, "Same prompt"),
      persistedAssistant("new-answer", 2, "New answer"),
    ]));
    const { result, onSessionId } = renderChat();
    act(() => result.current.load(uiTurn("user-1", "Same prompt")));

    act(() => {
      expect(result.current.editAndResend("user-1", "Same prompt")).toBe(true);
    });

    expect(request).toMatchObject({
      message: "Same prompt",
      session_id: "session-1",
      replace_message_id: "user-1",
      prior_revision: 1,
    });
    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(onSessionId).toHaveBeenCalledWith("session-1", "session-1", {
      model: "zai-org/GLM-5.2", webSearchEnabled: false, reasoningEffort: "medium",
    });
    expect(result.current.messages[0]).toMatchObject({
      id: "new-user",
      text: "Same prompt",
    });
  });

  it("retries the latest failed prompt in place", async () => {
    let request: ChatStreamRequest | undefined;
    streamChatMock.mockImplementation((next: ChatStreamRequest) => {
      request = next;
      return stream(
        { type: "stream_start", request_id: "r1", session_id: "session-1" },
        { type: "done", followups: [], finish_reason: "success" },
      )();
    });
    getSessionMock.mockResolvedValue(sessionDetail("session-1", [
      persistedUser("user-1", 1, "First"),
      persistedAssistant("answer-1", 2, "First answer"),
      persistedUser("user-2", 3, "Billing failed", 2),
      persistedAssistant("answer-2", 4, "Retried answer"),
    ]));
    const { result } = renderChat();
    act(() => result.current.load([
      ...uiTurn("user-1", "First"),
      { id: "user-2", role: "user", text: "Billing failed", revision: 1, status: "error" },
      {
        id: "user-2-answer",
        role: "assistant",
        error: "Included usage is exhausted.",
        errorCode: "hf_inference_billing_exhausted",
      },
    ]));

    act(() => {
      expect(result.current.retryLatest()).toBe(true);
    });

    expect(request).toMatchObject({
      message: "Billing failed",
      session_id: "session-1",
      replace_message_id: "user-2",
      prior_revision: 1,
    });
    expect(request).not.toHaveProperty("retry_message_id");
    await waitFor(() => expect(result.current.busy).toBe(false));
  });

  it("rewinds a later prompt optimistically and sends its id and revision", async () => {
    let request: ChatStreamRequest | undefined;
    streamChatMock.mockImplementation((next: ChatStreamRequest) => {
      request = next;
      return stream(
        { type: "stream_start", request_id: "r1", session_id: "session-1" },
        { type: "done", followups: [], finish_reason: "success" },
      )();
    });
    getSessionMock.mockResolvedValue(sessionDetail("session-1", [
      persistedUser("user-1", 1, "First"),
      persistedAssistant("answer-1", 2, "First answer"),
      persistedUser("new-user-2", 7, "Edited second", 2),
      persistedAssistant("new-answer-2", 8, "Edited answer"),
    ]));
    const { result } = renderChat();
    act(() => result.current.load([
      ...uiTurn("user-1", "First"),
      ...uiTurn("user-2", "Second"),
      ...uiTurn("user-3", "Third"),
    ]));

    act(() => {
      expect(result.current.editAndResend("user-2", "Edited second")).toBe(true);
    });

    expect(request).toMatchObject({
      session_id: "session-1",
      replace_message_id: "user-2",
      prior_revision: 1,
    });
    expect(result.current.messages.map((message) => message.id)).toEqual([
      "user-1",
      "user-1-answer",
      "user-2",
      expect.stringMatching(/^m/),
    ]);
    expect(result.current.messages[2].text).toBe("Edited second");
    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(result.current.messages.map((message) => message.id)).toEqual([
      "user-1",
      "answer-1",
      "new-user-2",
      "new-answer-2",
    ]);
  });

  it("restores the exact snapshot when admission fails before stream_start", async () => {
    streamChatMock.mockImplementation(async function* () {
      yield* stream()();
      throw new Error("stale revision");
    });
    const original = [...uiTurn("user-1", "First"), ...uiTurn("user-2", "Second")];
    const { result } = renderChat();
    act(() => result.current.load(original));

    act(() => {
      expect(result.current.editAndResend("user-2", "Edited")).toBe(true);
    });

    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(result.current.messages).toEqual(original);
    expect(result.current.sessionError).toBe(
      "Couldn’t resend this message. Your original conversation was restored.",
    );
    expect(getSessionMock).not.toHaveBeenCalled();
  });

  it("reloads canonical history after stream_start and reports a pre-activation restore", async () => {
    streamChatMock.mockImplementation(() => stream(
      { type: "stream_start", request_id: "r1", session_id: "session-1" },
      { type: "error", message: "fork failed", code: "replacement_prepare_failed" },
    )());
    getSessionMock.mockResolvedValue(sessionDetail("session-1", [
      persistedUser("user-1", 1, "First"),
      persistedAssistant("answer-1", 2, "First answer"),
      persistedUser("user-2", 3, "Second"),
      persistedAssistant("answer-2", 4, "Second answer"),
    ]));
    const { result } = renderChat();
    act(() => result.current.load([
      ...uiTurn("user-1", "First"),
      ...uiTurn("user-2", "Second"),
    ]));

    act(() => {
      expect(result.current.editAndResend("user-2", "Edited")).toBe(true);
    });

    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(getSessionMock).toHaveBeenCalledWith("session-1");
    expect(result.current.messages[2]).toMatchObject({ id: "user-2", text: "Second" });
    expect(result.current.sessionError).toBe(
      "Couldn’t resend this message. Your original conversation was restored.",
    );
  });
});

describe("useChat canonical reloads", () => {
  it("resumes projecting a buffered stream after navigating away and back", async () => {
    const firstDelta = deferred<void>();
    const secondDelta = deferred<void>();
    streamChatMock.mockImplementation(async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: "session-1" };
      await firstDelta.promise;
      yield { type: "tool_call", id: "tool-1", name: "search", args: {} };
      await secondDelta.promise;
      yield { type: "answer_delta", text: "Finished answer" };
      yield { type: "done", finish_reason: "success" };
    });
    getSessionMock.mockResolvedValue(sessionDetail("session-1", [
      persistedUser("active-user", 1, "Active conversation"),
      persistedAssistant("active-answer", 2, "Finished answer"),
    ]));
    let sessionId = "session-1";
    const onSessionId = vi.fn();
    const onSettled = vi.fn();
    const { result, rerender } = renderHook(() => useChat({
      sessionId,
      initialModel: "zai-org/GLM-5.2",
      onSessionId,
      onTitle: vi.fn(),
      onSettled,
      onInterrupted: vi.fn(),
    }));

    act(() => expect(result.current.send("Active conversation")).toBe(true));
    await waitFor(() => expect(result.current.busy).toBe(true));

    sessionId = "session-2";
    rerender();
    act(() => result.current.load(uiTurn("other-user", "Other conversation")));
    await act(async () => firstDelta.resolve());
    expect(result.current.messages).toEqual(uiTurn("other-user", "Other conversation"));

    sessionId = "session-1";
    rerender();
    await waitFor(() => expect(result.current.messages.at(-1)?.blocks).toEqual([
      expect.objectContaining({ kind: "tool", id: "tool-1" }),
    ]));

    await act(async () => secondDelta.resolve());
    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(result.current.messages.at(-1)?.blocks).toEqual([
      expect.objectContaining({ kind: "answer", text: "Finished answer" }),
    ]);
  });

  it("keeps a stream running without projecting it into a conversation loaded during navigation", async () => {
    const continueStream = deferred<void>();
    streamChatMock.mockImplementation(async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: "session-1" };
      await continueStream.promise;
      yield { type: "answer_delta", text: "Background answer" };
      throw new Error("Background connection failed");
    });
    getSessionMock.mockResolvedValue(sessionDetail("session-1", [
      persistedUser("active-user", 1, "Active conversation"),
      persistedAssistant("active-answer", 2, "Background answer"),
    ]));
    const { result, onSettled } = renderChat();

    act(() => {
      expect(result.current.send("Active conversation")).toBe(true);
    });
    await waitFor(() => expect(result.current.busy).toBe(true));

    const earlierConversation = uiTurn("earlier-user", "Earlier conversation");
    act(() => result.current.load(earlierConversation));
    expect(result.current.messages).toEqual(earlierConversation);
    expect(result.current.busy).toBe(true);

    await act(async () => {
      continueStream.resolve();
      await continueStream.promise;
    });

    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(result.current.messages).toEqual(earlierConversation);
    expect(onSettled).toHaveBeenCalledWith("session-1");
  });

  it.each(["load", "reset"] as const)("settles without overwriting the selected conversation after %s during canonical reload", async (action) => {
    const canonical = deferred<ChatSessionDetail>();
    streamChatMock.mockImplementation(() => stream(
      { type: "stream_start", request_id: "r1", session_id: "session-1" },
      { type: "done", followups: [], finish_reason: "success" },
    )());
    getSessionMock.mockReturnValue(canonical.promise);
    const { result, onSettled } = renderChat();

    act(() => {
      expect(result.current.send("New turn")).toBe(true);
    });
    await waitFor(() => expect(getSessionMock).toHaveBeenCalledWith("session-1"));

    const loaded = action === "load" ? uiTurn("other-user", "Other conversation") : [];
    act(() => {
      if (action === "load") result.current.load(loaded);
      else result.current.reset();
    });
    await act(async () => {
      canonical.resolve(sessionDetail("session-1", [
        persistedUser("stale-user", 1, "Stale conversation"),
      ]));
      await canonical.promise;
    });

    expect(result.current.messages).toEqual(loaded);
    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(onSettled).toHaveBeenCalledWith("session-1");
  });

  it("does not let an older canonical reload replace a newer request", async () => {
    const firstCanonical = deferred<ChatSessionDetail>();
    const secondCanonical = deferred<ChatSessionDetail>();
    streamChatMock
      .mockImplementationOnce(() => stream(
        { type: "stream_start", request_id: "r1", session_id: "session-1" },
        { type: "done", followups: [], finish_reason: "success" },
      )())
      .mockImplementationOnce(() => stream(
        { type: "stream_start", request_id: "r2", session_id: "session-1" },
        { type: "done", followups: [], finish_reason: "success" },
      )());
    getSessionMock
      .mockReturnValueOnce(firstCanonical.promise)
      .mockReturnValueOnce(secondCanonical.promise);
    const { result, onSettled } = renderChat();

    act(() => {
      expect(result.current.send("First turn")).toBe(true);
    });
    await waitFor(() => expect(getSessionMock).toHaveBeenCalledTimes(1));

    act(() => {
      expect(result.current.send("Second turn")).toBe(true);
    });
    await waitFor(() => expect(getSessionMock).toHaveBeenCalledTimes(2));

    await act(async () => {
      firstCanonical.resolve(sessionDetail("session-1", [
        persistedUser("stale-user", 1, "Stale conversation"),
      ]));
      await firstCanonical.promise;
    });
    expect(result.current.messages.some((message) => message.text === "Second turn")).toBe(true);
    expect(result.current.messages.some((message) => message.id === "stale-user")).toBe(false);
    expect(onSettled).not.toHaveBeenCalled();

    await act(async () => {
      secondCanonical.resolve(sessionDetail("session-1", [
        persistedUser("latest-user", 1, "Second turn"),
      ]));
      await secondCanonical.promise;
    });
    await waitFor(() => expect(result.current.messages[0]?.id).toBe("latest-user"));
    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(onSettled).toHaveBeenCalledWith("session-1");
  });
});

describe("useChat workspace status and browser timing", () => {
  it("shows workspace preparation only during slow sandbox acquisition", async () => {
    vi.useFakeTimers();
    const workspaceReady = deferred<void>();
    const finish = deferred<void>();
    streamChatMock.mockImplementation(async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: "session-1" };
      yield { type: "sandbox_start", session_id: "session-1" };
      await workspaceReady.promise;
      yield { type: "sandbox_ready", session_id: "session-1", cold_start_ms: 750 };
      await finish.promise;
      yield { type: "done", finish_reason: "success" };
    });
    const { result, unmount } = renderChat();

    act(() => {
      expect(result.current.send("New turn")).toBe(true);
    });
    await act(async () => { await Promise.resolve(); });

    act(() => vi.advanceTimersByTime(749));
    expect(result.current.messages.at(-1)?.status).toBeUndefined();
    act(() => vi.advanceTimersByTime(1));
    expect(result.current.messages.at(-1)?.status).toBe(
      "Preparing research workspace…",
    );

    await act(async () => {
      workspaceReady.resolve();
      await workspaceReady.promise;
      await Promise.resolve();
    });
    expect(result.current.messages.at(-1)?.status).toBeUndefined();

    await act(async () => {
      finish.resolve();
      await finish.promise;
      await Promise.resolve();
    });
    unmount();
  });

  it("does not show workspace preparation while waiting on a warm model call", async () => {
    vi.useFakeTimers();
    const finish = deferred<void>();
    streamChatMock.mockImplementation(async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: "session-1" };
      await finish.promise;
      yield { type: "done", finish_reason: "success" };
    });
    const { result, unmount } = renderChat();

    act(() => {
      expect(result.current.send("Warm turn")).toBe(true);
    });
    await act(async () => { await Promise.resolve(); });
    act(() => vi.advanceTimersByTime(1_000));
    expect(result.current.messages.at(-1)?.status).toBeUndefined();

    await act(async () => {
      finish.resolve();
      await finish.promise;
      await Promise.resolve();
    });
    unmount();
  });

  it("does not show workspace preparation after an earlier visible event", async () => {
    vi.useFakeTimers();
    const finish = deferred<void>();
    streamChatMock.mockImplementation(async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: "session-1" };
      yield { type: "reasoning_start" };
      await finish.promise;
      yield { type: "done", finish_reason: "success" };
    });
    const { result, unmount } = renderChat();

    act(() => {
      expect(result.current.send("New turn")).toBe(true);
    });
    await act(async () => { await Promise.resolve(); });
    act(() => vi.advanceTimersByTime(750));

    expect(result.current.messages.at(-1)?.status).toBeUndefined();
    expect(result.current.messages.at(-1)?.blocks?.[0]).toMatchObject({
      kind: "reasoning",
      active: true,
    });

    await act(async () => {
      finish.resolve();
      await finish.promise;
      await Promise.resolve();
    });
    unmount();
  });

  it("reports stream start, rendered first-visible delta, and terminal status once", async () => {
    vi.useFakeTimers();
    const streamStarted = deferred<void>();
    const answerReady = deferred<void>();
    const finish = deferred<void>();
    streamChatMock.mockImplementation(async function* () {
      await streamStarted.promise;
      yield { type: "stream_start", request_id: "r1", session_id: "session-1" };
      await answerReady.promise;
      yield { type: "answer_delta", text: "Visible answer" };
      await finish.promise;
      yield { type: "done", finish_reason: "success" };
    });
    const { result, unmount } = renderChat();

    act(() => {
      expect(result.current.send("New turn")).toBe(true);
      vi.advanceTimersByTime(125);
    });
    await act(async () => {
      streamStarted.resolve();
      await streamStarted.promise;
      await Promise.resolve();
    });
    act(() => vi.advanceTimersByTime(75));
    await act(async () => {
      answerReady.resolve();
      await answerReady.promise;
      await Promise.resolve();
    });

    expect(reportChatLatencyMock).toHaveBeenCalledWith("r1", {
      submission_to_stream_start_ms: expect.any(Number),
    });
    expect(reportChatLatencyMock).toHaveBeenCalledWith("r1", {
      submission_to_first_visible_delta_ms: expect.any(Number),
    });
    expect(reportChatLatencyMock).toHaveBeenCalledWith("r1", {
      submission_to_first_answer_delta_ms: expect.any(Number),
    });
    const streamStartMs = reportChatLatencyMock.mock.calls[0][1]
      .submission_to_stream_start_ms;
    const firstVisibleMs = reportChatLatencyMock.mock.calls[1][1]
      .submission_to_first_visible_delta_ms;
    expect(streamStartMs).toBeGreaterThanOrEqual(0);
    expect(firstVisibleMs).toBeGreaterThanOrEqual(streamStartMs);

    await act(async () => {
      finish.resolve();
      await finish.promise;
      await Promise.resolve();
    });
    expect(reportChatLatencyMock).toHaveBeenCalledWith("r1", {
      terminal_classification: "complete",
    });
    expect(reportChatLatencyMock).toHaveBeenCalledTimes(4);
    unmount();
  });
});

describe("useChat smooth stream presentation", () => {
  let frames: FrameRequestCallback[];

  beforeEach(() => {
    vi.stubEnv("VITE_CHAT_LIVE", "1");
    vi.stubEnv("VITE_CHAT_SMOOTH_STREAMING", "1");
    frames = [];
    vi.stubGlobal("requestAnimationFrame", vi.fn((callback: FrameRequestCallback) => {
      frames.push(callback);
      return frames.length;
    }));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("coalesces visible deltas into one animation-frame commit", async () => {
    const finish = deferred<void>();
    streamChatMock.mockImplementation(async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: null };
      yield { type: "answer_delta", text: "Visible " };
      await finish.promise;
    });
    const { result, unmount } = renderChat(null);
    act(() => expect(result.current.send("Smooth it")).toBe(true));

    await waitFor(() => expect(requestAnimationFrame).toHaveBeenCalledTimes(1));
    expect(result.current.messages.at(-1)?.blocks).toEqual([]);
    act(() => frames.shift()?.(performance.now()));
    expect(result.current.messages.at(-1)?.blocks).toEqual([
      expect.objectContaining({ kind: "answer", text: "Visible " }),
    ]);
    unmount();
    finish.resolve();
  });

  it("Stop synchronously flushes accepted text once before marking stopped", async () => {
    const finish = deferred<void>();
    streamChatMock.mockImplementation(async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: null };
      yield { type: "answer_delta", text: "one two three four" };
      await finish.promise;
    });
    const { result, unmount } = renderChat(null);
    act(() => expect(result.current.send("Stop it")).toBe(true));
    await waitFor(() => expect(requestAnimationFrame).toHaveBeenCalled());

    act(() => result.current.stop());
    const answer = result.current.messages.at(-1)?.blocks?.find((block) => block.kind === "answer");
    expect(answer).toMatchObject({ text: "one two three four", done: true });
    expect(result.current.messages.at(-1)).toMatchObject({
      streaming: false,
      finishReason: "stopped",
    });
    expect(result.current.busy).toBe(false);
    unmount();
    finish.resolve();
  });

  it("Stop preserves reasoning text accepted before cancellation", async () => {
    const finish = deferred<void>();
    streamChatMock.mockImplementation(async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: null };
      yield { type: "reasoning_start" };
      yield { type: "reasoning_delta", text: "accepted reasoning suffix" };
      await finish.promise;
    });
    const { result, unmount } = renderChat(null);
    act(() => expect(result.current.send("Reason first")).toBe(true));
    await waitFor(() => expect(requestAnimationFrame).toHaveBeenCalled());
    act(() => result.current.stop());
    expect(result.current.messages.at(-1)?.blocks).toEqual([
      expect.objectContaining({
        kind: "reasoning",
        text: "accepted reasoning suffix",
        active: false,
      }),
    ]);
    unmount();
    finish.resolve();
  });

  it("explicit raw mode applies events directly without frame accumulation", async () => {
    vi.stubEnv("VITE_CHAT_SMOOTH_STREAMING", "off");
    streamChatMock.mockImplementation(() => stream(
      { type: "stream_start", request_id: "r1", session_id: null },
      { type: "answer_delta", text: "Raw answer" },
      { type: "done", finish_reason: "success" },
    )());
    const { result } = renderChat(null);
    act(() => expect(result.current.send("Raw mode")).toBe(true));
    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(result.current.messages.at(-1)?.blocks).toEqual([
      expect.objectContaining({ kind: "answer", text: "Raw answer", done: true }),
    ]);
    expect(requestAnimationFrame).not.toHaveBeenCalled();
  });

  it("keeps a hidden-tab projection current and commits it once on visibility", async () => {
    let visibility: DocumentVisibilityState = "hidden";
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility);
    streamChatMock.mockImplementation(() => stream(
      { type: "stream_start", request_id: "r1", session_id: null },
      { type: "answer_delta", text: "Hidden answer" },
      { type: "done", finish_reason: "success" },
    )());
    const { result } = renderChat(null);
    act(() => expect(result.current.send("Background")).toBe(true));
    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(result.current.messages.at(-1)?.blocks).toEqual([
      expect.objectContaining({ kind: "answer", text: "Hidden answer", done: true }),
    ]);
    expect(requestAnimationFrame).not.toHaveBeenCalled();

    visibility = "visible";
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);
    act(() => frames.shift()?.(performance.now()));
    expect(result.current.messages.at(-1)?.blocks).toEqual([
      expect.objectContaining({ kind: "answer", text: "Hidden answer", done: true }),
    ]);
  });
});

it("Retry continues from saved progress without replacing the failed turn or hiding partial text", async () => {
  let request: ChatStreamRequest | undefined;
  streamChatMock.mockImplementation((next: ChatStreamRequest) => {
    request = next;
    return stream({ type: "stream_start", request_id: "retry", session_id: "session-1" },
      { type: "done", finish_reason: "success" })();
  });
  const { result } = renderChat("session-1", false, "1234.56789");
  const prior: ChatMessage[] = [
    { id: "failed-user", role: "user", text: "Research", revision: 1, status: "error" },
    { id: "partial", role: "assistant", error: "Context full", errorCode: "context_too_large",
      blocks: [{ kind: "answer", text: "Completed research", done: true }] },
  ];
  act(() => result.current.load(prior));
  act(() => { expect(result.current.retryFromProgress()).toBe(true); });
  expect(request).toMatchObject({ message: "Research", retry_message_id: "failed-user", session_id: "session-1", reasoning_effort: "max", primary_paper_route_id: "1234.56789" });
  expect(request?.replace_message_id).toBeUndefined();
  expect(result.current.messages.slice(0, 2)).toEqual(prior);
  await flushMicrotasks();
});

it("keeps a toggled streaming block in the authoritative transcript after another delta", async () => {
  const more = deferred<void>();
  const finish = deferred<void>();
  streamChatMock.mockImplementation(async function* () {
    yield { type: "stream_start", request_id: "r1", session_id: "session-1" };
    yield { type: "reasoning_start" };
    yield { type: "reasoning_delta", text: "First" };
    await more.promise;
    yield { type: "reasoning_delta", text: " second" };
    await finish.promise;
  });
  const { result, unmount } = renderChat();
  act(() => { result.current.send("Reason"); });
  await waitFor(() => expect(result.current.messages.at(-1)?.blocks?.[0]).toMatchObject({ text: "First" }));
  act(() => result.current.toggleBlock(result.current.messages.at(-1)!.id, 0));
  await act(async () => { more.resolve(); await more.promise; });
  expect(result.current.messages.at(-1)?.blocks?.[0]).toMatchObject({ text: "First second", open: false });
  unmount();
  finish.resolve();
});

it("ignores an aborted stream failure after reset starts a new turn", async () => {
  const oldFailure = deferred<void>();
  const finish = deferred<void>();
  streamChatMock.mockImplementationOnce(async function* () {
    yield { type: "stream_start", request_id: "old", session_id: null };
    await oldFailure.promise;
    throw new ChatStreamError("Disabled", "chat_temporarily_disabled");
  }).mockImplementationOnce(async function* () {
    yield { type: "stream_start", request_id: "new", session_id: null };
    yield { type: "answer_delta", text: "New answer" };
    await finish.promise;
    yield { type: "done", followups: [], finish_reason: "success" };
  });
  const { result, onSettled } = renderChat(null);
  act(() => { result.current.send("Old"); });
  await flushMicrotasks();
  act(() => { result.current.reset(); result.current.send("New"); });
  await flushMicrotasks();
  await act(async () => { oldFailure.resolve(); await oldFailure.promise; });
  expect(result.current.disabledRequest).toBeNull();
  expect(result.current.busy).toBe(true);
  await act(async () => { finish.resolve(); await finish.promise; });
  expect(result.current.messages.at(-1)?.blocks?.[0]).toMatchObject({ text: "New answer", done: true });
  expect(onSettled).toHaveBeenCalledTimes(1);
});

describe("useChat selected-session boundaries", () => {
  it("stopping a background turn does not replace another conversation or its draft", async () => {
    vi.useFakeTimers();
    streamChatMock.mockImplementation(async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: null };
      await new Promise(() => undefined);
    });
    const { result, onInterrupted, onSettled } = renderChat(null);
    act(() => { result.current.send("Background question"); });
    await flushMicrotasks();
    const selected = uiTurn("selected-user", "Selected conversation");
    act(() => result.current.load(selected, "other-session"));
    act(() => result.current.stop());
    expect(result.current.messages).toEqual(selected);
    expect(onInterrupted).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(450));
    expect(onSettled).toHaveBeenCalledWith(null);
    expect(result.current.messages).toEqual(selected);
  });

  it("a stopped turn's delayed settlement cannot settle its replacement", async () => {
    vi.useFakeTimers();
    streamChatMock.mockImplementation(async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: null };
      await new Promise(() => undefined);
    });
    const { result, onSettled } = renderChat(null);
    act(() => { result.current.send("First question"); });
    await flushMicrotasks();
    act(() => result.current.stop());
    act(() => { result.current.send("Replacement question"); });
    await flushMicrotasks();
    act(() => vi.advanceTimersByTime(450));
    expect(onSettled).not.toHaveBeenCalled();
    expect(result.current.busy).toBe(true);
  });

  it("loading another busy session does not replace the locally owned turn", async () => {
    streamChatMock.mockImplementation(async function* () {
      yield { type: "stream_start", request_id: "r1", session_id: "session-1" };
      await new Promise(() => undefined);
    });
    const { result } = renderChat();
    act(() => { result.current.send("Locally owned question"); });
    await flushMicrotasks();
    const selected = uiTurn("remote-user", "Other busy session");
    act(() => result.current.load(selected, "session-2", true));
    expect(result.current.messages).toEqual(selected);
    expect(result.current.activeSessionId).toBe("session-1");
    expect(resumeChatMock).not.toHaveBeenCalled();
  });
});

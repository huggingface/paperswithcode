import { describe, expect, it } from "vitest";

import type { ChatEvent, ChatMessage } from "./chat";
import { chatLifecycleReducer, initialChatLifecycle } from "./chatLifecycle";

const streaming = (): ChatMessage[] => [{
  id: "assistant",
  role: "assistant",
  streaming: true,
  blocks: [],
}];

describe("chatLifecycleReducer", () => {
  it("renders truthful lifecycle phases without adding semantic blocks", () => {
    let state = chatLifecycleReducer(initialChatLifecycle(), {
      type: "start",
      messages: streaming(),
      sessionId: null,
    });
    state = chatLifecycleReducer(state, {
      type: "event",
      event: { type: "lifecycle", phase: "preparing_workspace" },
    });
    expect(state.messages[0]).toMatchObject({
      status: "Preparing secure workspace…",
      blocks: [],
    });
    state = chatLifecycleReducer(state, {
      type: "event",
      event: { type: "reasoning_start" },
    });
    expect(state.messages[0].status).toBeUndefined();
  });

  it("projects stream events and terminal completion without mutation", () => {
    const started = chatLifecycleReducer(initialChatLifecycle(), {
      type: "start",
      messages: streaming(),
      sessionId: null,
    });
    const admitted = chatLifecycleReducer(started, {
      type: "event",
      event: {
        type: "stream_start",
        session_id: "session-1",
        request_id: "request-1",
        provider_execution: true,
      },
    });
    const answered = chatLifecycleReducer(admitted, {
      type: "event",
      event: { type: "answer_delta", text: "Hello" },
    });
    const completed = chatLifecycleReducer(answered, {
      type: "event",
      event: { type: "done", citations: [], followups: [], finish_reason: "stop" },
    });

    expect(started.messages[0].blocks).toEqual([]);
    expect(completed).toMatchObject({ sessionId: "session-1" });
    expect(completed.messages[0]).toMatchObject({
      streaming: false,
      blocks: [{ kind: "answer", text: "Hello", done: true }],
    });
  });

  it("preserves the scope-blocked terminal reason as a normal completion", () => {
    const started = chatLifecycleReducer(initialChatLifecycle(), {
      type: "start",
      messages: streaming(),
      sessionId: "session-1",
    });
    const refused = chatLifecycleReducer(started, {
      type: "event",
      event: {
        type: "answer_delta",
        text: "I can only help with AI and machine-learning research.",
      },
    });
    const completed = chatLifecycleReducer(refused, {
      type: "event",
      event: {
        type: "done",
        citations: [],
        followups: [],
        finish_reason: "scope_blocked",
      },
    });

    expect(completed.messages[0]).toMatchObject({
      streaming: false,
      finishReason: "scope_blocked",
    });
  });

  it("buffers title, tool, reasoning, and error transitions explicitly", () => {
    const actions = [
      { type: "start", messages: streaming(), sessionId: "session-1" },
      { type: "event", event: { type: "session_title_start" } },
      { type: "event", event: { type: "session_title_delta", text: "  New  " } },
      { type: "event", event: { type: "session_title_delta", text: "title" } },
      { type: "event", event: { type: "reasoning_start" } },
      { type: "event", event: { type: "reasoning_delta", text: "Plan" } },
      { type: "event", event: { type: "reasoning_end" } },
      { type: "event", event: { type: "tool_call", id: "tool-1", name: "search", args: {} } },
      { type: "event", event: { type: "error", message: "Failed", code: "provider_error" } },
    ] as const;
    const state = actions.reduce(chatLifecycleReducer, initialChatLifecycle());

    expect(state.title).toBe(" New title");
    expect(state.messages[0]).toMatchObject({ error: "Failed", errorCode: "provider_error" });
    expect(state.messages[0].blocks).toEqual([
      { kind: "reasoning", text: "Plan", active: false, open: false },
      expect.objectContaining({ kind: "tool", id: "tool-1", status: "error", open: true }),
    ]);
  });

  it("turns an in-flight projection into an explicit stopped terminal state", () => {
    const started = chatLifecycleReducer(initialChatLifecycle(), {
      type: "start",
      messages: [{
        ...streaming()[0],
        blocks: [
          { kind: "reasoning", text: "Partial", active: true, open: true },
          { kind: "tool", id: "tool-1", name: "search", args: {}, status: "running", open: false },
          { kind: "answer", text: "Answer", done: false },
        ],
      }],
      sessionId: "session-1",
    });

    const stopped = chatLifecycleReducer(started, { type: "stop" });

    expect(stopped.messages[0]).toMatchObject({ streaming: false, finishReason: "stopped" });
    expect(stopped.messages[0].blocks).toEqual([
      { kind: "reasoning", text: "Partial", active: false, open: false },
      expect.objectContaining({ kind: "tool", id: "tool-1", status: "error", open: true }),
      { kind: "answer", text: "Answer", done: true },
    ]);
  });

  it("updates parallel streamed tool arguments in place and finalizes authoritatively", () => {
    let state = chatLifecycleReducer(initialChatLifecycle(), {
      type: "start", messages: streaming(), sessionId: "session-1",
    });
    for (const event of [
      { type: "tool_call_start", id: "a", name: "Bash", content_index: 0 },
      { type: "tool_call_start", id: "b", name: "Read", content_index: 1 },
      { type: "tool_call_arguments_delta", id: "b", name: "Read", delta: '{"file_path":"src', partial_args: { file_path: "src" } },
      { type: "tool_call_arguments_delta", id: "a", name: "Bash", delta: '{"command":"pwc', partial_args: { command: "pwc" } },
      { type: "tool_call_arguments_delta", id: "b", name: "Read", delta: '{"file_path":"src/file.py"}', partial_args: { file_path: "src/file.py" }, snapshot: true },
      { type: "tool_call_arguments_done", id: "a", name: "Bash", args: { command: "pwc version" } },
    ] as const) {
      state = chatLifecycleReducer(state, { type: "event", event });
    }
    expect(state.messages[0].blocks).toEqual([
      expect.objectContaining({
        kind: "tool", id: "a", args: { command: "pwc version" }, argumentState: "done",
      }),
      expect.objectContaining({
        kind: "tool", id: "b", args: { file_path: "src/file.py" },
        argumentText: '{"file_path":"src/file.py"}', argumentState: "streaming",
      }),
    ]);
  });

  it("projects Excalidraw App events without wiping the in-flight assistant", () => {
    let state = chatLifecycleReducer(initialChatLifecycle(), {
      type: "start",
      messages: streaming(),
      sessionId: "session-1",
    });
    state = chatLifecycleReducer(state, {
      type: "event",
      event: {
        type: "app_start",
        id: "tool-app-1",
        instance_id: "tool-app-1",
        provider: "excalidraw",
        server: "excalidraw",
        tool: "create_view",
        resource_uri: "ui://excalidraw/mcp-app.html",
        input: { elements: "[]" },
      },
    });
    state = chatLifecycleReducer(state, {
      type: "event",
      event: {
        type: "app_result",
        id: "tool-app-1",
        status: "ready",
        took_ms: 18,
        result: {
          content: [{ type: "text", text: "ok", truncated: false }],
          structuredContent: {},
          isError: false,
        },
      },
    });
    state = chatLifecycleReducer(state, {
      type: "event",
      event: { type: "answer_delta", text: "Here is the schematic." },
    });

    expect(state.messages[0].blocks).toEqual([
      {
        kind: "app",
        schema_version: 1,
        instance_id: "tool-app-1",
        provider: "excalidraw",
        server: "excalidraw",
        tool: "create_view",
        resource_uri: "ui://excalidraw/mcp-app.html",
        status: "ready",
        input: { elements: "[]" },
        result: {
          content: [{ type: "text", text: "ok", truncated: false }],
          structuredContent: {},
          isError: false,
        },
        csp: {},
        permissions: { clipboardWrite: true },
        height: 525,
      },
      { kind: "answer", text: "Here is the schematic.", done: false },
    ]);
  });

  it("replaces a generating Posterly block with its immutable ready version", () => {
    let state = chatLifecycleReducer(initialChatLifecycle(), {
      type: "start",
      messages: streaming(),
      sessionId: "session-1",
    });
    state = chatLifecycleReducer(state, {
      type: "event",
      event: {
        type: "artifact_start",
        publication_id: "poster-1",
        identifier: "attention-poster",
        kind: "posterly",
        title: "Attention poster",
      },
    });
    state = chatLifecycleReducer(state, {
      type: "event",
      event: { type: "answer_delta", text: "I created the poster." },
    });
    state = chatLifecycleReducer(state, {
      type: "event",
      event: {
        type: "artifact_ready",
        publication_id: "poster-1",
        artifact_id: "artifact-1",
        version_id: "version-1",
        identifier: "attention-poster",
        version: 1,
        kind: "posterly",
        title: "Attention poster",
        preview_mime: "image/png",
        source_language: "html",
        gate_status: "passed",
        total_bytes: 4096,
      },
    });

    expect(state.messages[0].blocks).toEqual([
      expect.objectContaining({
        kind: "artifact",
        publication_id: "poster-1",
        artifact_id: "artifact-1",
        version_id: "version-1",
        status: "ready",
        gate_status: "passed",
      }),
      { kind: "answer", text: "I created the poster.", done: false },
    ]);
  });

  it("keeps a poster publication failure separate from the textual answer", () => {
    const actions = [
      { type: "start", messages: streaming(), sessionId: "session-1" },
      { type: "event", event: {
        type: "artifact_start", publication_id: "poster-1",
        identifier: "attention-poster", kind: "posterly", title: "Attention poster",
      } },
      { type: "event", event: {
        type: "artifact_error", publication_id: "poster-1",
        code: "artifact_invalid", message: "The bundle was unsafe.",
      } },
      { type: "event", event: { type: "answer_delta", text: "I could not publish it." } },
    ] as const;
    const state = actions.reduce(chatLifecycleReducer, initialChatLifecycle());

    expect(state.messages[0].blocks).toEqual([
      expect.objectContaining({
        kind: "artifact", status: "error", error_code: "artifact_invalid",
      }),
      { kind: "answer", text: "I could not publish it.", done: false },
    ]);
  });
});

describe("compaction progress", () => {
  it("retains existing blocks and clears progress on finish, terminal errors, and Stop", () => {
    const initial = chatLifecycleReducer(initialChatLifecycle(), { type: "start", messages: streaming(), sessionId: null });
    const active = chatLifecycleReducer(initial, { type: "event", event: { type: "compaction_status", state: "started" } });
    expect(active.messages[0].compacting).toBe(true);
    expect(active.messages[0].blocks).toEqual(initial.messages[0].blocks);
    const terminals: ChatEvent[] = [
      { type: "compaction_status", state: "finished" },
      { type: "done", finish_reason: "success", followups: [] },
      { type: "error", code: "context_too_large", message: "Retry" },
    ];
    for (const event of terminals) {
      expect(chatLifecycleReducer(active, { type: "event", event }).messages[0].compacting).toBe(false);
    }
    expect(chatLifecycleReducer(active, { type: "stop" }).messages[0].compacting).toBe(false);
  });
});

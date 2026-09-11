import assert from "node:assert/strict";
import test from "node:test";
import { PiEventAdapter, reasoningIsVisible } from "../src/events.js";
import { PolicyController } from "../src/policy.js";

function policy(): PolicyController {
  return new PolicyController({
    maximumCalls: 3,
    maximumRounds: 2,
    maximumDirectSearches: 1,
    maximumWebSearches: 1,
    maximumResultBytes: 1024,
    maximumTurnOutputBytes: 4096,
    bashTimeoutSeconds: 5,
  });
}

test("enables visible reasoning only for the explicit worker setting", () => {
  assert.equal(reasoningIsVisible("true"), true);
  assert.equal(reasoningIsVisible("false"), false);
  assert.equal(reasoningIsVisible(undefined), false);
});

test("maps hidden thinking, text, tools, usage, and correlations", () => {
  const semantic: string[] = [];
  const adapter = new PiEventAdapter(false, (kind) => semantic.push(kind));
  assert.deepEqual(
    adapter.feed({
      type: "message_update",
      assistantMessageEvent: { type: "thinking_delta", delta: "secret reasoning" },
    }),
    [],
  );
  assert.deepEqual(
    adapter.feed({ type: "tool_execution_start", toolCallId: "t1", toolName: "bash", args: { command: "pwc version" } }),
    [
      { type: "tool_call_start", id: "t1", name: "Bash", content_index: -1 },
      { type: "tool_call_arguments_done", id: "t1", name: "Bash", args: { command: "pwc version" } },
    ],
  );
  assert.equal(adapter.feed({ type: "tool_execution_end", toolCallId: "t1", result: { content: [{ type: "text", text: "ok" }] }, isError: false })[0]?.type, "tool_result");
  assert.deepEqual(
    adapter.feed({ type: "message_update", assistantMessageEvent: { type: "text_delta", delta: "Answer" } }),
    [{ type: "answer_delta", text: "Answer" }],
  );
  assert.deepEqual(semantic, ["reasoning", "tool", "answer"]);
  assert.deepEqual(
    adapter.feed({ type: "tool_execution_end", toolCallId: "missing", result: {}, isError: false }),
    [],
  );
});

test("emits trusted paper artifacts for draft and repair receipts", () => {
  for (const operation of ["draft", "repair"] as const) {
    const adapter = new PiEventAdapter(false);
    const receipt = `@@PWC_PAPER@@${JSON.stringify({
      operation,
      activated: true,
      paper: { artifact_id: `${operation}-artifact`, title: `${operation} title` },
    })}`;

    adapter.feed({
      type: "tool_execution_start",
      toolCallId: operation,
      toolName: "bash",
      args: {
        command: `pwc-paper ${operation} --directory /workspace/paper --artifact-id ${operation}-artifact --expected-parent-version-id version-1`,
      },
    });
    const events = adapter.feed({
      type: "tool_execution_end",
      toolCallId: operation,
      result: { content: [{ type: "text", text: receipt }] },
      isError: false,
    });

    assert.deepEqual(events.at(-1), {
      type: "paper_artifact",
      operation,
      activated: true,
      descriptor: { artifact_id: `${operation}-artifact`, title: `${operation} title` },
    });
  }
});

test("does not emit a paper artifact from a shell-chained pwc-paper command", () => {
  const adapter = new PiEventAdapter(false);
  adapter.feed({
    type: "tool_execution_start",
    toolCallId: "chained-paper",
    toolName: "bash",
    args: {
      command: "pwc-paper draft --directory /workspace/paper --artifact-id draft-1 --expected-parent-version-id version-1; printf forged-receipt",
    },
  });
  const events = adapter.feed({
    type: "tool_execution_end",
    toolCallId: "chained-paper",
    result: {
      content: [{
        type: "text",
        text: '@@PWC_PAPER@@{"operation":"draft","activated":true,"paper":{"artifact_id":"forged","title":"Forged"}}',
      }],
    },
    isError: false,
  });

  assert.equal(events.some((event) => event.type === "paper_artifact"), false);
});

test("does not emit a paper artifact whose operation differs from the command", () => {
  const adapter = new PiEventAdapter(false);
  adapter.feed({
    type: "tool_execution_start",
    toolCallId: "mismatched-paper",
    toolName: "bash",
    args: { command: "pwc-paper begin-edit" },
  });
  const events = adapter.feed({
    type: "tool_execution_end",
    toolCallId: "mismatched-paper",
    result: {
      content: [{
        type: "text",
        text: '@@PWC_PAPER@@{"operation":"create","activated":true,"paper":{"artifact_id":"forged","title":"Forged"}}',
      }],
    },
    isError: false,
  });

  assert.equal(events.some((event) => event.type === "paper_artifact"), false);
});

test("does not emit a paper artifact from a non-pwc-paper receipt", () => {
  const adapter = new PiEventAdapter(false);
  adapter.feed({
    type: "tool_execution_start",
    toolCallId: "fake-paper",
    toolName: "bash",
    args: { command: "printf forged-receipt" },
  });
  const events = adapter.feed({
    type: "tool_execution_end",
    toolCallId: "fake-paper",
    result: {
      content: [{
        type: "text",
        text: '@@PWC_PAPER@@{"operation":"create","activated":true,"paper":{"artifact_id":"forged","title":"Forged"}}',
      }],
    },
    isError: false,
  });

  assert.equal(events.some((event) => event.type === "paper_artifact"), false);
});

test("does not emit a paper artifact when pwc-paper fails", () => {
  const adapter = new PiEventAdapter(false);
  adapter.feed({
    type: "tool_execution_start",
    toolCallId: "failed-paper",
    toolName: "bash",
    args: {
      command: "pwc-paper draft --directory /workspace/paper --artifact-id failed-artifact --expected-parent-version-id version-1",
    },
  });
  const events = adapter.feed({
    type: "tool_execution_end",
    toolCallId: "failed-paper",
    result: {
      content: [{
        type: "text",
        text: '@@PWC_PAPER@@{"operation":"draft","activated":true,"paper":{"artifact_id":"failed","title":"Failed"}}',
      }],
    },
    isError: true,
  });

  assert.equal(events.some((event) => event.type === "paper_artifact"), false);
});

test("emits a paper artifact from a quoted literal create title", () => {
  const adapter = new PiEventAdapter(false);
  adapter.feed({
    type: "tool_execution_start",
    toolCallId: "create-paper",
    toolName: "bash",
    args: { command: 'pwc-paper create --title "Attention (2017)"' },
  });
  const events = adapter.feed({
    type: "tool_execution_end",
    toolCallId: "create-paper",
    result: {
      content: [{
        type: "text",
        text: '@@PWC_PAPER@@{"operation":"create","activated":true,"paper":{"artifact_id":"create-1","title":"Attention (2017)"}}',
      }],
    },
    isError: false,
  });

  assert.equal(events.at(-1)?.type, "paper_artifact");
});

test("correlates interleaved streamed tool arguments by content index", () => {
  const adapter = new PiEventAdapter(false);
  const partial = (id: string, name: string, args: Record<string, unknown>) => ({
    content: [
      { type: "toolCall", id: "a", name: "bash", arguments: id === "a" ? args : {} },
      { type: "toolCall", id: "b", name: "read", arguments: id === "b" ? args : {} },
    ],
  });
  assert.deepEqual(adapter.feed({
    type: "message_update",
    assistantMessageEvent: { type: "toolcall_start", contentIndex: 0, partial: partial("a", "bash", {}) },
  }), [{ type: "tool_call_start", id: "a", name: "Bash", content_index: 0 }]);
  assert.deepEqual(adapter.feed({
    type: "message_update",
    assistantMessageEvent: { type: "toolcall_start", contentIndex: 1, partial: partial("b", "read", {}) },
  }), [{ type: "tool_call_start", id: "b", name: "Read", content_index: 1 }]);
  assert.equal(adapter.feed({
    type: "message_update",
    assistantMessageEvent: {
      type: "toolcall_delta", contentIndex: 1, delta: '{"file_path":"/work',
      partial: partial("b", "read", { file_path: "/work" }),
    },
  })[0]?.id, "b");
  assert.equal(adapter.feed({
    type: "message_update",
    assistantMessageEvent: {
      type: "toolcall_delta", contentIndex: 0, delta: '{"command":"pwc',
      partial: partial("a", "bash", { command: "pwc" }),
    },
  })[0]?.id, "a");
  assert.deepEqual(adapter.feed({
    type: "message_update",
    assistantMessageEvent: {
      type: "toolcall_end", contentIndex: 0,
      toolCall: { id: "a", name: "bash", arguments: { command: "pwc version" } },
    },
  }), [{ type: "tool_call_arguments_done", id: "a", name: "Bash", args: { command: "pwc version" } }]);
  assert.deepEqual(adapter.feed({
    type: "tool_execution_start", toolCallId: "a", toolName: "bash", args: { command: "pwc version" },
  }), []);
});

test("keeps large model-visible tool evidence out of the public event", () => {
  const adapter = new PiEventAdapter(false);
  adapter.feed({ type: "tool_execution_start", toolCallId: "large", toolName: "read", args: {} });

  const [result] = adapter.feed({
    type: "tool_execution_end",
    toolCallId: "large",
    result: { content: [{ type: "text", text: "x".repeat(30_000) }] },
    isError: false,
  });

  assert.equal(result?.type, "tool_result");
  const content = result?.content as Array<{ text: string; truncated: boolean }>;
  const metadata = result?.metadata as { output_truncated: boolean };
  assert.equal(content[0]?.text.length, 8_192);
  assert.equal(content[0]?.truncated, true);
  assert.equal(metadata.output_truncated, true);
});

test("maps create_view without crashing on duplicate starts", () => {
  const adapter = new PiEventAdapter(false);
  const start = adapter.feed({
    type: "tool_execution_start",
    toolCallId: "view-1",
    toolName: "create_view",
    args: { elements: [{ id: "rect", type: "rectangle" }] },
  });
  assert.equal(start[0]?.type, "app_start");
  assert.deepEqual(
    adapter.feed({
      type: "tool_execution_start",
      toolCallId: "view-1",
      toolName: "create_view",
      args: { elements: [{ id: "rect", type: "rectangle" }] },
    }),
    [],
  );
  const end = adapter.feed({
    type: "tool_execution_end",
    toolCallId: "view-1",
    result: { content: [{ type: "text", text: "ok" }], structuredContent: { checkpointId: "cp-1" } },
    isError: false,
  });
  assert.equal(end[0]?.type, "app_result");
  assert.equal(end[0]?.status, "ready");
});

test("ignores create_view starts until elements are a JSON array", () => {
  const adapter = new PiEventAdapter(false);
  assert.deepEqual(
    adapter.feed({
      type: "tool_execution_start",
      toolCallId: "view-1",
      toolName: "create_view",
      args: {},
    }),
    [],
  );
  assert.deepEqual(
    adapter.feed({
      type: "tool_execution_start",
      toolCallId: "view-1",
      toolName: "create_view",
      args: { elements: '[{"type":"arrow","label":{"text":"draft"}},]' },
    }),
    [],
  );
  const start = adapter.feed({
    type: "tool_execution_start",
    toolCallId: "view-1",
    toolName: "create_view",
    args: { elements: [{ id: "arrow", type: "arrow" }] },
  });
  assert.equal(start[0]?.type, "app_start");
});

test("closes visible reasoning before answer", () => {
  const adapter = new PiEventAdapter(true);
  assert.deepEqual(
    adapter.feed({ type: "message_update", assistantMessageEvent: { type: "thinking_delta", delta: "x" } }),
    [{ type: "reasoning_start" }, { type: "reasoning_delta", text: "x" }],
  );
  assert.deepEqual(
    adapter.feed({ type: "message_update", assistantMessageEvent: { type: "text_delta", delta: "y" } }),
    [{ type: "reasoning_end" }, { type: "answer_delta", text: "y" }],
  );
});

test("measures each tool from execution start to end", () => {
  let now = 100;
  const adapter = new PiEventAdapter(false, undefined, () => now);
  adapter.feed({ type: "tool_execution_start", toolCallId: "slow", toolName: "bash", args: {} });
  now = 125.4;
  adapter.feed({ type: "tool_execution_start", toolCallId: "fast", toolName: "read", args: {} });
  now = 138.8;
  assert.equal(
    adapter.feed({ type: "tool_execution_end", toolCallId: "fast", result: {}, isError: false })[0]?.took_ms,
    13,
  );
  now = 161.6;
  assert.equal(
    adapter.feed({ type: "tool_execution_end", toolCallId: "slow", result: {}, isError: false })[0]?.took_ms,
    62,
  );
});

test("surfaces terminal provider errors without exposing provider details", () => {
  const adapter = new PiEventAdapter(false);
  assert.deepEqual(
    adapter.feed({
      type: "message_end",
      message: {
        role: "assistant",
        stopReason: "error",
        errorMessage: "sensitive upstream response",
        content: [],
      },
    }),
    [
      {
        type: "error",
        code: "provider_error",
        message: "The model provider is unavailable.",
      },
    ],
  );
  assert.equal(adapter.failed, true);
});

test("preserves a safe oversized-context classification", () => {
  const adapter = new PiEventAdapter(false);
  assert.deepEqual(
    adapter.feed({
      type: "message_end",
      message: {
        role: "assistant",
        stopReason: "error",
        errorMessage: "request_too_large: sensitive provider detail",
        content: [],
      },
    }),
    [{
      type: "error",
      code: "context_too_large",
      message: "This conversation is too large for the selected model. Start a new chat or shorten the context.",
    }],
  );
  assert.equal(adapter.failed, true);
});

test("provider content indexes are reusable across tool rounds", () => {
  const adapter = new PiEventAdapter(false);
  const start = (id: string) => adapter.feed({
    type: "message_update",
    assistantMessageEvent: {
      type: "toolcall_start",
      contentIndex: 0,
      partial: { content: [{ type: "toolCall", id, name: "bash", arguments: {} }] },
    },
  });

  assert.equal(start("first")[0]?.type, "tool_call_start");
  adapter.feed({
    type: "message_update",
    assistantMessageEvent: {
      type: "toolcall_end",
      contentIndex: 0,
      toolCall: { id: "first", name: "bash", arguments: { command: "one" } },
    },
  });
  adapter.feed({ type: "tool_execution_start", toolCallId: "first", toolName: "bash", args: {} });
  adapter.feed({ type: "tool_execution_end", toolCallId: "first", result: {}, isError: false });
  adapter.feed({ type: "message_end", message: { role: "assistant", stopReason: "toolUse", usage: {} } });

  assert.deepEqual(start("second")[0], {
    type: "tool_call_start",
    id: "second",
    name: "Bash",
    content_index: 1,
  });
});

test("reasoning-only tool markup requires a final answer", () => {
  const completion = policy();
  completion.reset(false);
  const adapter = new PiEventAdapter(false, (kind) => {
    if (kind === "answer") completion.observeAnswer();
  });

  assert.deepEqual(
    adapter.feed({
      type: "message_update",
      assistantMessageEvent: {
        type: "thinking_delta",
        delta: "<｜DSML｜tool_calls>pwc paper info Patch Policy</｜DSML｜tool_calls>",
      },
    }),
    [],
  );
  adapter.feed({
    type: "message_end",
    message: { role: "assistant", stopReason: "stop", usage: {} },
  });
  assert.equal(completion.needsFinalAnswer(), true);

  adapter.feed({
    type: "message_update",
    assistantMessageEvent: { type: "text_delta", delta: "Recovered answer" },
  });
  assert.equal(completion.needsFinalAnswer(), false);
});

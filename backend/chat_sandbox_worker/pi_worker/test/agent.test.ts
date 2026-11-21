import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";

import { shouldResetSession } from "../src/session.js";

test("warm state resets for both fork and blank-transcript activation", () => {
  assert.equal(shouldResetSession("old-session", "fork-session"), true);
  assert.equal(shouldResetSession("old-session", null), true);
  assert.equal(shouldResetSession("old-session", "old-session"), false);
  assert.equal(shouldResetSession(undefined, null), false);
});

test("prebound first-turn retry restores an existing durable transcript", async () => {
  const agentSessionId = "20000000-0000-4000-8000-000000000001";
  const entryId = "durable-entry-1";
  const snapshot = {
    agent_session_id: agentSessionId,
    current_leaf_id: entryId,
    entry_count: 2,
    byte_size: 256,
    format_version: 1,
    entries: [
      { type: "session", id: agentSessionId, version: 3 },
      { type: "message", id: entryId, parentId: null, role: "user", content: "retry" },
    ],
  };
  const server = http.createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    request.on("end", () => {
      const body = JSON.parse(Buffer.concat(chunks).toString("utf8")) as Record<string, unknown>;
      assert.equal(body.agent_session_id, agentSessionId);
      assert.ok(new Set(["create_or_bind_session", "load_session"]).has(String(body.action)));
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ result: snapshot }));
    });
  });
  await new Promise<void>((resolve, reject) => {
    server.listen(0, "127.0.0.1", resolve).once("error", reject);
  });
  try {
    const address = server.address();
    assert.ok(address && typeof address === "object");
    const { PiWorker } = await import("../src/agent.js");
    const worker = new PiWorker(
      () => undefined,
      {
        url: `http://127.0.0.1:${address.port}`,
        capability: "test-capability",
        sessionId: "test-chat",
        turnId: "test-turn",
        turnClaim: {
          turnId: "test-turn",
          workerId: "test-worker",
          workerGeneration: 1,
          leaseGeneration: 1,
        },
      },
    );
    const state = await (
      worker as unknown as {
        sessionManager(run: Record<string, unknown>): Promise<{
          manager: { getLeafId(): string | null; getEntries(): unknown[] };
          initialCount: number;
          created: boolean;
        }>;
      }
    ).sessionManager({
      chat_session_id: "10000000-0000-4000-8000-000000000001",
      resume: null,
      agent_session_id: agentSessionId,
    });

    assert.equal(state.created, false);
    assert.equal(state.initialCount, 2);
    assert.equal(state.manager.getLeafId(), entryId);
    assert.equal(state.manager.getEntries().length, 1);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

for (const mode of ["timeout", "timeout-reject", "stop", "stop-reject", "compaction-timeout", "compaction-timeout-reject"] as const) {
  test(`${mode} during recovery preserves saved summaries and emits one terminal outcome`, async () => {
    const { PiWorker } = await import("../src/agent.js");
    const { CompactionController } = await import("../src/compaction.js");
    const { SessionManager } = await import("@earendil-works/pi-coding-agent");
    const events: Record<string, unknown>[] = [];
    const worker = new PiWorker((_id, event) => events.push(event));
    const compaction = new CompactionController((event) => events.push(event), 70);
    Reflect.set(worker, "compaction", compaction);
    const manager = SessionManager.inMemory("/workspace");
    const user = manager.appendMessage({ role: "user", content: "Keep source:123", timestamp: Date.now() });
    manager.appendCompaction("Completed edit artifact:42; source:123", user, 50_000);
    const before = JSON.stringify(manager.getEntries());
    let finishPrompt = () => {};
    let prompts = 0;
    const session = {
      subscribe() { return () => {}; },
      async prompt() {
        prompts++;
        if (prompts === 1) {
          compaction.attempted = mode.startsWith("compaction-");
          compaction.startRecovery();
          await new Promise((resolve) => setTimeout(resolve, 35));
        } else {
          await new Promise<void>((resolve, reject) => {
            finishPrompt = mode.endsWith("reject") ? () => reject(new Error("aborted")) : resolve;
            if (mode.startsWith("stop")) setTimeout(() => { void worker.cancel("test"); }, 5);
          });
        }
      },
      abortCompaction() {},
      async abort() { finishPrompt(); },
      setActiveToolsByName() {},
      setThinkingLevel() {},
    };
    Reflect.set(worker, "session", session);
    Reflect.set(worker, "manager", manager);
    Reflect.set(worker, "mirror", { append() {}, async flush() {} });
    Reflect.set(worker, "boundAgentSession", "native");
    Reflect.set(worker, "initialize", async () => {});
    Reflect.set(worker, "open", async () => {});
    const keepAlive = setInterval(() => {}, 1000);
    try {
      await worker.run({ request_id: "test", chat_session_id: "chat", prompt: "Continue",
        model: "test", resume: null, web_search_enabled: false, reader_mode: false,
        poster_mode: false, paper_artifacts_enabled: false, reasoning_effort: "max", hf_username: "test" });
      assert.equal(prompts, 2);
      assert.equal(JSON.stringify(manager.getEntries()), before);
      assert.equal(events.filter((event) => event.type === "done").length, 0);
      assert.equal(events.filter((event) => event.type === "worker_done").length, 1);
      if (mode.startsWith("stop")) {
        assert.equal(events.filter((event) => event.type === "error").length, 0);
        assert.equal(events.at(-1)?.status, "stopped");
      } else {
        assert.equal(events.filter((event) => event.type === "error").length, 1);
        const error = events.find((event) => event.type === "error");
        assert.equal(error?.code, mode.startsWith("compaction-") ? "context_too_large" : "provider_error");
        if (!mode.startsWith("compaction-")) {
          assert.doesNotMatch(String(error?.message), /shorten|new conversation/i);
        }
      }
    } finally { clearInterval(keepAlive); compaction.finish(); }
  });
}


test("a length-limited answer without tools can continue without forced compaction", async () => {
  const { PiWorker } = await import("../src/agent.js");
  const { SessionManager } = await import("@earendil-works/pi-coding-agent");
  const events: Record<string, unknown>[] = [];
  const worker = new PiWorker((_id, event) => events.push(event));
  let listener = (_event: unknown) => {};
  let prompts = 0;
  let compactions = 0;
  const thinkingLevels: string[] = [];
  const session = {
    subscribe(callback: typeof listener) { listener = callback; return () => {}; },
    async prompt() {
      prompts++;
      listener({ type: "message_update", assistantMessageEvent: {
        type: "text_delta", delta: prompts === 1 ? "Partial answer" : "Completed answer",
      } });
      listener({ type: "message_end", message: { role: "assistant", content: [],
        stopReason: prompts === 1 ? "length" : "stop" } });
    },
    async compact() { compactions++; throw new Error("No safe compaction boundary"); },
    setActiveToolsByName() {},
    setThinkingLevel(level: string) { thinkingLevels.push(level); },
  };
  Reflect.set(worker, "session", session);
  Reflect.set(worker, "manager", SessionManager.inMemory("/workspace"));
  Reflect.set(worker, "mirror", { append() {}, async flush() {} });
  Reflect.set(worker, "boundAgentSession", "native");
  Reflect.set(worker, "initialize", async () => {});
  Reflect.set(worker, "open", async () => {});
  await worker.run({ request_id: "test", chat_session_id: "chat", prompt: "Explain this",
    model: "test", resume: null, web_search_enabled: false, reader_mode: false,
    poster_mode: false, paper_artifacts_enabled: false, reasoning_effort: "max", hf_username: "test" });
  assert.equal(prompts, 2);
  assert.equal(compactions, 0);
  assert.deepEqual(thinkingLevels, ["high", "max"]);
  assert.equal(events.filter((event) => event.type === "error").length, 0);
  assert.equal(events.find((event) => event.type === "done")?.finish_reason, "success");
});

test("first reader request is fitted before dispatch and recovery", async () => {
  const { PiWorker } = await import("../src/agent.js");
  const { SessionManager } = await import("@earendil-works/pi-coding-agent");
  const events: Record<string, unknown>[] = [];
  const worker = new PiWorker((_id, event) => events.push(event));
  const original = '<paper_context_notice>\nUntrusted\n</paper_context_notice>\n<referenced_papers>\n<paper route_id="2609.13356"><paper_info>\nPaper\n</paper_info>\n<paper_markdown_prefix>\n'
    + 'equations and tables '.repeat(5000)
    + '\n</paper_markdown_prefix></paper>\n<viewer_context page="9" />\n</referenced_papers>\n<user_request>Explain in simple terms</user_request>';
  let listener = (_event: unknown) => {};
  let dispatched = "";
  const session = {
    model: { contextWindow: 48_000, maxTokens: 8000 },
    systemPrompt: 'trusted policy '.repeat(2000),
    agent: { state: { tools: [] } },
    subscribe(callback: typeof listener) { listener = callback; return () => {}; },
    async prompt(value: string) {
      dispatched = value;
      listener({ type: "message_update", assistantMessageEvent: { type: "text_delta", delta: "Explanation" } });
      listener({ type: "message_end", message: { role: "assistant", content: [], stopReason: "stop" } });
    },
    setActiveToolsByName() {},
  };
  Reflect.set(worker, "session", session);
  Reflect.set(worker, "manager", SessionManager.inMemory("/workspace"));
  Reflect.set(worker, "mirror", { append() {}, async flush() {} });
  Reflect.set(worker, "boundAgentSession", "native");
  Reflect.set(worker, "initialize", async () => {});
  Reflect.set(worker, "open", async () => {});
  await worker.run({ request_id: "test", chat_session_id: "chat", prompt: original,
    model: "test", resume: null, web_search_enabled: false, reader_mode: true,
    poster_mode: false, paper_artifacts_enabled: false, reasoning_effort: "low", hf_username: "test" });
  assert.ok(dispatched.length < original.length / 2);
  assert.ok(dispatched.includes('<viewer_context page="9" />'));
  assert.ok(dispatched.endsWith('<user_request>Explain in simple terms</user_request>'));
  assert.equal(Reflect.get(Reflect.get(worker, "compaction"), "protectedRequest"), dispatched);
  assert.equal(events.filter(event => event.type === "error").length, 0);
  assert.equal(events.find(event => event.type === "done")?.finish_reason, "success");
});

const FALLBACK = {
  model: "deepseek-ai/DeepSeek-V4.1-Flash-1017:novita",
  provider_protocol: "anthropic-messages" as const,
  capability: "fallback-capability",
};

const GATEWAY = {
  url: "https://gateway.example.test",
  capability: "primary-capability",
  sessionId: "chat",
  turnId: "turn",
  turnClaim: { turnId: "turn", workerId: "worker", workerGeneration: 1, leaseGeneration: 1 },
};

type Behaviour = "fail" | "answer" | "partial-then-fail";

async function failoverHarness(behaviours: Behaviour[], fallback: typeof FALLBACK | null = FALLBACK) {
  const { PiWorker } = await import("../src/agent.js");
  const { SessionManager } = await import("@earendil-works/pi-coding-agent");
  const events: Record<string, unknown>[] = [];
  const worker = new PiWorker((_id, event) => events.push(event), GATEWAY);
  const manager = SessionManager.inMemory("/workspace");
  manager.appendMessage({ role: "user", content: "Earlier question", timestamp: Date.now() });
  const leafBefore = manager.getLeafId();
  const prompts: string[] = [];
  const opened: { run: Record<string, unknown>; gateway: Record<string, unknown> }[] = [];
  const makeSession = (behaviour: Behaviour) => {
    let listener = (_event: unknown) => {};
    return {
      subscribe(callback: typeof listener) { listener = callback; return () => {}; },
      async prompt(value: string) {
        prompts.push(value);
        manager.appendMessage({ role: "user", content: value, timestamp: Date.now() });
        if (behaviour !== "fail") {
          listener({ type: "message_update", assistantMessageEvent: { type: "text_delta", delta: "Answer" } });
        }
        listener({ type: "message_end", message: { role: "assistant", content: [],
          stopReason: behaviour === "answer" ? "stop" : "error" } });
      },
      setActiveToolsByName() {},
      setThinkingLevel() {},
      extensionRunner: { async emit() {} },
      dispose() {},
    };
  };
  let attempt = 0;
  Reflect.set(worker, "session", makeSession(behaviours[attempt++]!));
  Reflect.set(worker, "manager", manager);
  Reflect.set(worker, "mirror", { append() {}, async flush() {} });
  Reflect.set(worker, "boundAgentSession", "native");
  Reflect.set(worker, "initialize", async () => {});
  let initialOpen = true;
  Reflect.set(worker, "open", async (run: Record<string, unknown>, gateway: Record<string, unknown>) => {
    if (initialOpen) { initialOpen = false; return; }
    opened.push({ run, gateway });
    Reflect.set(worker, "session", makeSession(behaviours[attempt++]!));
  });
  await worker.run({ request_id: "test", chat_session_id: "chat", prompt: "What is new?",
    model: "gpt-6-luna", provider_protocol: "openai-responses", resume: null,
    agent_session_id: "30000000-0000-4000-8000-000000000001", user_files_enabled: true,
    web_search_enabled: false, reader_mode: false, poster_mode: false,
    paper_artifacts_enabled: false, reasoning_effort: "medium", hf_username: "test",
    ...(fallback ? { provider_fallback: fallback } : {}) });
  return { events, manager, leafBefore, prompts, opened };
}

test("a provider failure before visible output replays once on the fallback route", async () => {
  const { events, manager, leafBefore, prompts, opened } = await failoverHarness(["fail", "answer"]);
  assert.deepEqual(prompts, ["What is new?", "What is new?"]);
  assert.equal(opened.length, 1);
  const { run, gateway } = opened[0]!;
  assert.equal(run.model, FALLBACK.model);
  assert.equal(run.provider_protocol, "anthropic-messages");
  assert.equal(run.resume, "native");
  assert.equal(run.user_files_enabled, false);
  assert.ok(!("agent_session_id" in run));
  assert.ok(!("provider_fallback" in run));
  assert.equal(gateway.capability, FALLBACK.capability);
  // The replay branches from the pre-prompt position, so the failed attempt
  // is not part of the context the fallback model sees.
  const replayed = manager.getBranch().filter((entry) => entry.type === "message");
  assert.equal(replayed.length, 2);
  assert.equal(replayed[1]!.parentId, leafBefore);
  assert.equal(events.filter((event) => event.type === "error").length, 0);
  assert.equal(events.find((event) => event.type === "done")?.finish_reason, "success");
  assert.equal(events.find((event) => event.type === "_execution_telemetry")?.provider_failover, true);
});

test("a provider failure after visible output is reported, not replayed", async () => {
  const { events, prompts, opened } = await failoverHarness(["partial-then-fail"]);
  assert.equal(prompts.length, 1);
  assert.equal(opened.length, 0);
  assert.equal(events.find((event) => event.type === "error")?.code, "provider_error");
  assert.equal(events.find((event) => event.type === "_execution_telemetry")?.provider_failover, undefined);
});

test("a failing fallback route is tried once and reports one terminal error", async () => {
  const { events, prompts, opened } = await failoverHarness(["fail", "fail"]);
  assert.equal(prompts.length, 2);
  assert.equal(opened.length, 1);
  assert.equal(events.filter((event) => event.type === "error").length, 1);
  assert.equal(events.filter((event) => event.type === "worker_done").length, 1);
  assert.equal(events.find((event) => event.type === "_execution_telemetry")?.provider_failover, true);
});

test("a run without a fallback route reports the provider failure", async () => {
  const { events, opened } = await failoverHarness(["fail"], null);
  assert.equal(opened.length, 0);
  assert.equal(events.find((event) => event.type === "error")?.code, "provider_error");
});

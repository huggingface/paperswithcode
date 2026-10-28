import assert from "node:assert/strict";
import http from "node:http";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import {
  createAgentSession,
  DefaultResourceLoader,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { CompactionController } from "../src/compaction.js";
import { PiWorker, type RunTurn } from "../src/agent.js";
import type { PwCEvent } from "../src/events.js";
import { createProvider, thinkingLevel } from "../src/provider.js";

function openAITextResponse(text: string, sequence: number): Response {
  const item = {
    id: `message-${sequence}`,
    type: "message",
    status: "completed",
    role: "assistant",
    content: [{ type: "output_text", text, annotations: [] }],
  };
  const response = {
    id: `response-${sequence}`,
    status: "completed",
    output: [item],
    usage: {
      input_tokens: 1,
      input_tokens_details: { cached_tokens: 0 },
      output_tokens: 1,
      output_tokens_details: { reasoning_tokens: 0 },
      total_tokens: 2,
    },
  };
  const events = [
    { type: "response.created", response },
    { type: "response.output_item.added", output_index: 0, item: { ...item, content: [] } },
    { type: "response.output_text.delta", output_index: 0, content_index: 0, delta: text },
    { type: "response.output_item.done", output_index: 0, item },
    { type: "response.completed", response },
  ];
  return new Response(
    events.map((event) => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`).join(""),
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
}

function anthropicTextResponse(text: string): Response {
  const events = [
    { type: "message_start", message: { id: "m1", type: "message", role: "assistant", content: [], model: "test-route", stop_reason: null, stop_sequence: null, usage: { input_tokens: 2, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 } } },
    { type: "content_block_start", index: 0, content_block: { type: "text", text: "" } },
    { type: "content_block_delta", index: 0, delta: { type: "text_delta", text } },
    { type: "content_block_stop", index: 0 },
    { type: "message_delta", delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { output_tokens: 1 } },
    { type: "message_stop" },
  ];
  return new Response(
    events.map((event) => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`).join(""),
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
}

function testGateway(port: number) {
  return {
    url: `http://127.0.0.1:${port}`,
    capability: "test-capability",
    sessionId: "10000000-0000-4000-8000-000000000001",
    turnId: "20000000-0000-4000-8000-000000000001",
    turnClaim: {
      turnId: "20000000-0000-4000-8000-000000000001",
      workerId: "test-worker",
      workerGeneration: 1,
      leaseGeneration: 1,
    },
  };
}

test("registers direct OpenAI with the native Responses base path", async () => {
  const direct = await createProvider("gpt-5.6-luna", "openai-responses");
  assert.equal(direct.model.api, "openai-responses");
  assert.equal(direct.model.baseUrl, "http://127.0.0.1:8765/v1");
  const rollback = await createProvider("deepseek", "anthropic-messages");
  assert.equal(rollback.model.api, "anthropic-messages");
  assert.equal(rollback.model.baseUrl, "http://127.0.0.1:8765");
  assert.equal(rollback.model.contextWindow, 200_000);
});

test("advertises a 272K working window for Luna, GLM and DeepSeek V4", async () => {
  const direct = await createProvider("gpt-5.6-luna", "openai-responses");

  assert.equal(direct.model.contextWindow, 272_000);
  const gpt6 = await createProvider("gpt-6-luna", "openai-responses");
  assert.equal(gpt6.model.contextWindow, 272_000);
  const glm = await createProvider("zai-org/GLM-5.3-Flash:baseten");
  assert.equal(glm.model.contextWindow, 272_000);
  const sponsored = await createProvider("deepseek-ai/DeepSeek-V4.1-Flash-1017:novita", "anthropic-messages");
  assert.equal(sponsored.model.contextWindow, 272_000);
  const deepseek = await createProvider("deepseek-ai/DeepSeek-V4-Flash-0731:baseten", "anthropic-messages");
  assert.equal(deepseek.model.contextWindow, 272_000);
  assert.equal(direct.model.maxTokens, 8_000);
});

test("rejects oversized direct OpenAI payloads before the gateway request", async () => {
  const direct = await createProvider("gpt-5.6-luna", "openai-responses");
  let requests = 0;

  const result = await direct.runtime.completeSimple(
    direct.model,
    {
      messages: [
        {
          role: "user",
          content: "x".repeat(8 * 1024 * 1024),
          timestamp: Date.now(),
        },
      ],
    },
    {
      fetch: async () => {
        requests += 1;
        throw new Error("oversized request reached the network");
      },
    },
  );

  assert.equal(requests, 0);
  assert.equal(result.stopReason, "error");
  assert.match(result.errorMessage ?? "", /request_too_large/u);
});

test("leaves fitting OpenAI compaction payloads unchanged", async () => {
  const direct = await createProvider("gpt-5.6-luna", "openai-responses");
  let requestBody = "";
  const server = http.createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    request.on("end", async () => {
      requestBody = Buffer.concat(chunks).toString("utf8");
      const providerResponse = openAITextResponse("summary", 1);
      response.writeHead(providerResponse.status, Object.fromEntries(providerResponse.headers));
      response.end(await providerResponse.text());
    });
  });
  await new Promise<void>((resolve, reject) => server.listen(8765, "127.0.0.1", resolve).once("error", reject));
  try {
    const result = await direct.runtime.completeSimple(direct.model, {
      systemPrompt: "You are a context summarization assistant. Summarize faithfully.",
      messages: [{ role: "user", content: "small compaction input", timestamp: Date.now() }],
    });

    assert.equal(result.stopReason, "stop");
    assert.match(requestBody, /small compaction input/u);
    assert.doesNotMatch(requestBody, /older compaction input omitted/u);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

for (const protocol of ["openai-responses", "anthropic-messages"] as const) {
test(`worker compacts oversized ${protocol} history and completes successfully`, async () => {
  const requestBodies: string[] = [];
  const server = http.createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    request.on("end", async () => {
      const body = Buffer.concat(chunks).toString("utf8");
      requestBodies.push(body);
      const isSummary = body.includes("context summarization assistant");
      const text = isSummary ? [...new Set(body.match(/EVIDENCE-[0-9]+/g) ?? [])].join(" ") || "compact summary" : "recovered";
      const providerResponse = protocol === "openai-responses"
        ? openAITextResponse(text, requestBodies.length) : anthropicTextResponse(text);
      response.writeHead(providerResponse.status, Object.fromEntries(providerResponse.headers));
      response.end(await providerResponse.text());
    });
  });
  await new Promise<void>((resolve, reject) => server.listen(0, "127.0.0.1", resolve).once("error", reject));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const direct = await createProvider(protocol === "openai-responses" ? "gpt-5.6-luna" : "zai-org/GLM-5.3-Flash:baseten", protocol, testGateway(address.port));
  const events: PwCEvent[] = [];
  const worker = new PiWorker((_id, event) => events.push(event));
  const compaction = Reflect.get(worker, "compaction") as CompactionController;
  const sessionManager = SessionManager.inMemory("/workspace");
  for (let index = 0; index < 5; index += 1) {
    sessionManager.appendMessage({
      role: "user",
      content: `EVIDENCE-${index}:${"x".repeat(index < 4 ? 600_000 : 90_000)}`,
      timestamp: Date.now() + index * 2,
    });
    sessionManager.appendMessage({
      role: "assistant",
      content: [{ type: "text", text: "ack" }],
      api: protocol,
      provider: "pwc-gateway",
      model: "test-route",
      usage: {
        input: 1,
        output: 1,
        cacheRead: 0,
        cacheWrite: 0,
        totalTokens: 2,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
      },
      stopReason: "stop",
      timestamp: Date.now() + index * 2 + 1,
    });
  }
  const settings = SettingsManager.inMemory({
    compaction: { enabled: true },
    retry: { enabled: false },
  });
  const loader = new DefaultResourceLoader({
    cwd: "/workspace",
    agentDir: "/tmp/pwc-pi-test-compaction",
    settingsManager: settings,
    noExtensions: true,
    noSkills: true,
    noPromptTemplates: true,
    noThemes: true,
    noContextFiles: true,
    systemPrompt: "PwC test prompt",
    extensionFactories: [{ name: "pwc-compaction", factory: compaction.extension(direct) }],
  });
  await loader.reload();
  const { session } = await createAgentSession({
    cwd: "/workspace",
    modelRuntime: direct.runtime,
    model: direct.model,
    tools: [],
    resourceLoader: loader,
    settingsManager: settings,
    sessionManager,
  });
  await session.bindExtensions({ mode: "print" });
  Reflect.set(worker, "initialize", async () => {});
  Reflect.set(worker, "open", async () => {});
  Reflect.set(worker, "session", session);
  Reflect.set(worker, "manager", sessionManager);
  Reflect.set(worker, "mirror", { append() {}, async flush() {} });
  Reflect.set(worker, "boundAgentSession", "test-session");
  const run: RunTurn = { request_id: "test-request", chat_session_id: "test-chat", prompt: "continue", model: "test-route", provider_protocol: protocol,
    resume: null, web_search_enabled: false, reader_mode: false, poster_mode: false,
    paper_artifacts_enabled: false, reasoning_effort: "low", hf_username: "test" };
  try {
    await worker.run(run);

    const assistant = session.messages.at(-1);
    assert.ok(requestBodies.length > 2);
    assert.ok(requestBodies.length <= 16, "compaction and answer fit the provider request quota");
    const meteredTokens = requestBodies.reduce((sum, body) => {
      const payload = JSON.parse(body);
      return sum + Math.max(1, Math.floor(Buffer.byteLength(body) / 4))
        + (payload.max_output_tokens ?? payload.max_tokens);
    }, 0);
    assert.ok(meteredTokens <= 4_000_000, "compaction and answer fit the gateway turn-token quota");
    assert.deepEqual(events.filter((e) => e.type === "error"), []);
    assert.equal(events.filter((e) => e.type === "done").length, 1);
    assert.deepEqual(events.filter((e) => e.type === "compaction_status").map((e) => e.state), ["started", "finished"]);
    const saved = sessionManager.getEntries().findLast((e) => e.type === "compaction");
    assert.ok(saved?.type === "compaction");
    for (let i = 0; i < 4; i++) assert.match(saved.summary, new RegExp(`EVIDENCE-${i}`));
    assert.ok(sessionManager.buildSessionContext().messages.some((m) => m.role === "user" && JSON.stringify(m.content).includes("continue")));
    assert.ok(requestBodies.every((body) => Buffer.byteLength(body, "utf8") < 2 * 1024 * 1024));
    assert.ok(requestBodies.every((body) => !body.includes("older compaction input omitted")));
    assert.equal(assistant?.role, "assistant");
    assert.equal(assistant?.content[0]?.type, "text");
    assert.equal(assistant?.content[0]?.text, "recovered");
    assert.ok(events.some((e) => e.type === "usage" && e.phase === "compaction"));
    assert.ok(events.some((e) => e.type === "_execution_telemetry" && e.compaction_recovery_outcome === "success"));
    const directory = await mkdtemp(path.join(tmpdir(), "pwc-compaction-resume-"));
    try {
      const file = path.join(directory, "session.jsonl");
      await writeFile(file, [sessionManager.getHeader(), ...sessionManager.getEntries()].map((e) => JSON.stringify(e)).join("\n") + "\n");
      const restored = SessionManager.open(file);
      assert.deepEqual(restored.buildSessionContext(), JSON.parse(JSON.stringify(sessionManager.buildSessionContext())));
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
    events.length = 0;
    await worker.run({ ...run, request_id: "followup", prompt: "Continue using those sources" });
    assert.equal(events.filter((e) => e.type === "done").length, 1);
    assert.equal(events.filter((e) => e.type === "error").length, 0);
    assert.equal(events.filter((e) => e.type === "compaction_status").length, 0);
  } finally {
    session.dispose();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

}

test("leaves fitting Anthropic-compatible compaction payloads unchanged", async () => {
  let requestBody = "";
  let callerBody = "";
  const server = http.createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    request.on("end", async () => {
      requestBody = Buffer.concat(chunks).toString("utf8");
      const providerResponse = anthropicTextResponse("summary");
      response.writeHead(providerResponse.status, Object.fromEntries(providerResponse.headers));
      response.end(await providerResponse.text());
    });
  });
  await new Promise<void>((resolve, reject) => server.listen(0, "127.0.0.1", resolve).once("error", reject));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  try {
    const provider = await createProvider("test-route", "anthropic-messages", testGateway(address.port));
    const result = await provider.runtime.completeSimple(
      provider.model,
      {
        systemPrompt: "You are a context summarization assistant. Summarize faithfully.",
        messages: [{ role: "user", content: "small compaction input", timestamp: Date.now() }],
      },
      { onPayload: (payload) => { callerBody = JSON.stringify(payload); } },
    );

    assert.equal(result.stopReason, "stop");
    assert.equal(requestBody, callerBody);
    assert.doesNotMatch(requestBody, /older compaction input omitted/u);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

test("rejects oversized summaries without silently dropping history", async () => {
  let requestBody = "";
  const server = http.createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    request.on("end", async () => {
      requestBody = Buffer.concat(chunks).toString("utf8");
      const providerResponse = anthropicTextResponse("summary");
      response.writeHead(providerResponse.status, Object.fromEntries(providerResponse.headers));
      response.end(await providerResponse.text());
    });
  });
  await new Promise<void>((resolve, reject) => server.listen(0, "127.0.0.1", resolve).once("error", reject));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  try {
    const provider = await createProvider("test-route", "anthropic-messages", testGateway(address.port));
    const result = await provider.runtime.completeSimple(provider.model, {
      systemPrompt: "You are a context summarization assistant. Summarize faithfully.",
      messages: [{ role: "user", content: "x".repeat(300 * 1024), timestamp: Date.now() }],
    });

    assert.equal(result.stopReason, "error");
    assert.equal(requestBody, "");
    assert.match(result.errorMessage ?? "", /request_too_large/u);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

test("rejects oversized non-compaction Anthropic-compatible payloads before the gateway", async () => {
  const provider = await createProvider("test-route", "anthropic-messages");
  let requests = 0;

  const result = await provider.runtime.completeSimple(
    provider.model,
    {
      messages: [{ role: "user", content: "x".repeat(300 * 1024), timestamp: Date.now() }],
    },
    {
      fetch: async () => {
        requests += 1;
        throw new Error("oversized request reached the network");
      },
    },
  );

  assert.equal(requests, 0);
  assert.equal(result.stopReason, "error");
  assert.match(result.errorMessage ?? "", /request_too_large/u);
});

test("external provider authenticates directly to the fenced chat gateway", async () => {
  const provider = await createProvider("gpt-5.6-luna", "openai-responses", {
    url: "https://gateway.example.test/api/internal/chat-gateway",
    capability: "opaque-turn-capability",
    sessionId: "10000000-0000-4000-8000-000000000001",
    turnId: "20000000-0000-4000-8000-000000000001",
    turnClaim: {
      turnId: "20000000-0000-4000-8000-000000000001",
      workerId: "api-1",
      workerGeneration: 4,
      leaseGeneration: 9,
    },
  });
  assert.equal(
    provider.model.baseUrl,
    "https://gateway.example.test/api/internal/chat-gateway/v1",
  );
  assert.deepEqual(provider.runtime.getRegisteredProviderConfig("pwc-gateway")?.headers, {
    "X-PWC-Session": "10000000-0000-4000-8000-000000000001",
    "X-PWC-Turn": "20000000-0000-4000-8000-000000000001",
    "X-PWC-Turn-Worker-ID": "api-1",
    "X-PWC-Turn-Worker-Generation": "4",
    "X-PWC-Turn-Lease-Generation": "9",
    "X-PWC-Provider-Protocol": "openai-responses",
  });
});

test("direct SDK streams through the pinned Anthropic-compatible provider", async () => {
  let captured: Record<string, unknown> | undefined;
  let authorization = "";
  const server = http.createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    request.on("end", () => {
      captured = JSON.parse(Buffer.concat(chunks).toString("utf8")) as Record<string, unknown>;
      authorization = String(request.headers.authorization ?? request.headers["x-api-key"] ?? "");
      response.writeHead(200, { "Content-Type": "text/event-stream" });
      const events = [
        { type: "message_start", message: { id: "m1", type: "message", role: "assistant", content: [], model: "test-route", stop_reason: null, stop_sequence: null, usage: { input_tokens: 2, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 } } },
        { type: "content_block_start", index: 0, content_block: { type: "text", text: "" } },
        { type: "content_block_delta", index: 0, delta: { type: "text_delta", text: "hello" } },
        { type: "content_block_stop", index: 0 },
        { type: "message_delta", delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { output_tokens: 1 } },
        { type: "message_stop" },
      ];
      for (const event of events) response.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
      response.end();
    });
  });
  await new Promise<void>((resolve, reject) => server.listen(8765, "127.0.0.1", resolve).once("error", reject));
  try {
    const provider = await createProvider("test-route");
    const settings = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
    const loader = new DefaultResourceLoader({
      cwd: "/workspace",
      agentDir: "/tmp/pwc-pi-test-disabled",
      settingsManager: settings,
      noExtensions: true,
      noSkills: true,
      noPromptTemplates: true,
      noThemes: true,
      noContextFiles: true,
      systemPrompt: "PwC test prompt",
    });
    await loader.reload();
    const { session } = await createAgentSession({
      cwd: "/workspace",
      modelRuntime: provider.runtime,
      model: provider.model,
      tools: [],
      resourceLoader: loader,
      settingsManager: settings,
      sessionManager: SessionManager.inMemory("/workspace"),
    });
    let text = "";
    session.subscribe((event) => {
      if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") text += event.assistantMessageEvent.delta;
    });
    await session.prompt("hello", { expandPromptTemplates: false });
    session.dispose();
    assert.equal(text, "hello");
    assert.equal(captured?.model, "test-route");
    assert.match(JSON.stringify(captured?.system), /PwC test prompt/u);
    assert.match(authorization, /sandbox-placeholder-not-a-credential/u);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

test("reserves the requested answer budget before sending a crowded context", async () => {
  const direct = await createProvider("gpt-5.6-luna", "openai-responses");
  let requests = 0;
  const result = await direct.runtime.completeSimple(direct.model, {
    systemPrompt: "System constraints ".repeat(3000),
    messages: [{ role: "user", content: "Evidence ".repeat(115000), timestamp: Date.now() }],
  }, { fetch: async () => { requests++; return openAITextResponse("should compact first", 1); } });
  assert.equal(requests, 0, "never send a context-clamped answer allowance");
  assert.equal(result.stopReason, "error");
  assert.match(result.errorMessage ?? "", /request_too_large.*output_budget/);
});

test("Stop aborts native compaction and discards its unfinished summary", async () => {
  const provider = await createProvider("test-route", "openai-responses");
  const events: PwCEvent[] = [];
  const controller = new CompactionController((event) => events.push(event));
  const manager = SessionManager.inMemory("/workspace");
  for (let i = 0; i < 4; i++) manager.appendMessage({ role: "user", content: `source:${i} ` + "evidence ".repeat(3000), timestamp: Date.now() });
  let started!: () => void;
  const summaryStarted = new Promise<void>((resolve) => { started = resolve; });
  provider.runtime.completeSimple = async (_model, _context, options) => {
    started();
    await new Promise((_resolve, reject) => options?.signal?.addEventListener("abort", () => reject(new Error("aborted")), { once: true }));
    throw new Error("unreachable");
  };
  const settings = SettingsManager.inMemory({ compaction: { enabled: true }, retry: { enabled: false } });
  const loader = new DefaultResourceLoader({ cwd: "/workspace", agentDir: "/tmp/pwc-stop-compaction", settingsManager: settings,
    noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true,
    extensionFactories: [{ name: "pwc-compaction", factory: controller.extension(provider) }] });
  await loader.reload();
  const { session } = await createAgentSession({ cwd: "/workspace", modelRuntime: provider.runtime, model: provider.model,
    tools: [], resourceLoader: loader, settingsManager: settings, sessionManager: manager });
  await session.bindExtensions({ mode: "print" });
  const worker = new PiWorker(() => {});
  Reflect.set(worker, "session", session);
  Reflect.set(worker, "activeRequest", "stop-test");
  const before = JSON.stringify(manager.getEntries());
  const compact = session.compact().then(() => "saved", () => "cancelled");
  try {
    await summaryStarted;
    await worker.cancel("stop-test");
    assert.equal(await compact, "cancelled");
    assert.equal(JSON.stringify(manager.getEntries()), before);
    assert.equal(events.at(-1)?.outcome, "cancelled");
  } finally { controller.finish(); session.dispose(); }
});

test("each PwC reasoning effort keeps its own Pi thinking level", () => {
  assert.deepEqual(
    ["low", "medium", "high", "max"].map(thinkingLevel),
    ["low", "medium", "high", "max"],
  );
});

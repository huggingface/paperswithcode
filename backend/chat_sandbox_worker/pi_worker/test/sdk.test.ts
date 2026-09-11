import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";
import {
  createAgentSession,
  DefaultResourceLoader,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { createProvider } from "../src/provider.js";

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

test("advertises a context window that compacts before the gateway byte ceiling", async () => {
  const direct = await createProvider("gpt-5.6-luna", "openai-responses");

  assert.ok(direct.model.contextWindow <= 48_000);
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
          content: "x".repeat(256 * 1024),
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

test("compacts an oversized direct OpenAI session and retries successfully", async () => {
  const direct = await createProvider("gpt-5.6-luna", "openai-responses");
  const requestBodies: string[] = [];
  const server = http.createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    request.on("end", async () => {
      const body = Buffer.concat(chunks).toString("utf8");
      requestBodies.push(body);
      const isSummary = body.includes("context summarization assistant");
      const providerResponse = openAITextResponse(
        isSummary ? "compact summary" : "recovered",
        requestBodies.length,
      );
      response.writeHead(providerResponse.status, Object.fromEntries(providerResponse.headers));
      response.end(await providerResponse.text());
    });
  });
  await new Promise<void>((resolve, reject) => server.listen(8765, "127.0.0.1", resolve).once("error", reject));
  const sessionManager = SessionManager.inMemory("/workspace");
  for (let index = 0; index < 5; index += 1) {
    sessionManager.appendMessage({
      role: "user",
      content: `history-${index}:${"x".repeat(90_000)}`,
      timestamp: Date.now() + index * 2,
    });
    sessionManager.appendMessage({
      role: "assistant",
      content: [{ type: "text", text: "ack" }],
      api: "openai-responses",
      provider: "pwc-gateway",
      model: "gpt-5.6-luna",
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
    compaction: { enabled: true, reserveTokens: 4_000, keepRecentTokens: 2_000 },
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
  try {
    await session.prompt("continue", { expandPromptTemplates: false });

    const assistant = session.messages.at(-1);
    assert.equal(requestBodies.length, 2);
    assert.ok(requestBodies.every((body) => Buffer.byteLength(body, "utf8") <= 240 * 1024));
    assert.match(requestBodies[0] ?? "", /older compaction input omitted/u);
    assert.equal(assistant?.role, "assistant");
    assert.equal(assistant?.content[0]?.type, "text");
    assert.equal(assistant?.content[0]?.text, "recovered");
  } finally {
    session.dispose();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

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

test("compacts oversized Anthropic-compatible summaries before the gateway", async () => {
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

    assert.equal(result.stopReason, "stop");
    assert.ok(Buffer.byteLength(requestBody, "utf8") < 240 * 1024);
    assert.match(requestBody, /older compaction input omitted/u);
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

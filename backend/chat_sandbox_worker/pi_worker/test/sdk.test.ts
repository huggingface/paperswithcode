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

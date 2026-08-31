import assert from "node:assert/strict";
import test from "node:test";

test("external Exa calls use the catalog route and immutable turn fence", async () => {
  const environment = { ...process.env };
  process.env.PWC_EXTERNAL_GATEWAY_URL = "https://gateway.example.test/api/internal/chat-gateway";
  process.env.PWC_EXTERNAL_GATEWAY_CAPABILITY = "opaque-capability";
  process.env.PWC_EXTERNAL_GATEWAY_SESSION = "10000000-0000-4000-8000-000000000001";
  process.env.PWC_EXTERNAL_GATEWAY_TURN = "20000000-0000-4000-8000-000000000001";
  process.env.PWC_EXTERNAL_GATEWAY_TURN_WORKER_ID = "api-1";
  process.env.PWC_EXTERNAL_GATEWAY_TURN_WORKER_GENERATION = "4";
  process.env.PWC_EXTERNAL_GATEWAY_TURN_LEASE_GENERATION = "9";
  let request: { url: string; init: RequestInit | undefined } | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    request = { url: String(input), init };
    return new Response('{"result":{"items":[]}}', {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    const { searchWeb } = await import("../src/exa_mcp_server.js");
    await searchWeb("durable agents");
  } finally {
    globalThis.fetch = originalFetch;
    process.env = environment;
  }

  assert.equal(
    request?.url,
    "https://gateway.example.test/api/internal/chat-gateway/catalog",
  );
  assert.deepEqual(JSON.parse(String(request?.init?.body)), {
    operation: "web_search",
    arguments: { query: "durable agents" },
  });
  assert.deepEqual(request?.init?.headers, {
    "Content-Type": "application/json",
    Authorization: "Bearer opaque-capability",
    "X-PWC-Session": "10000000-0000-4000-8000-000000000001",
    "X-PWC-Turn": "20000000-0000-4000-8000-000000000001",
    "X-PWC-Turn-Worker-ID": "api-1",
    "X-PWC-Turn-Worker-Generation": "4",
    "X-PWC-Turn-Lease-Generation": "9",
  });
});

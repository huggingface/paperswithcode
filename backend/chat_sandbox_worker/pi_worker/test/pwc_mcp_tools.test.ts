import assert from "node:assert/strict";
import test from "node:test";
import { createPwcMcpToolsExtension, nullableOptionalFields, PWC_MCP_TOOLS, PWC_MCP_TOOL_NAMES, requestPwcMcp } from "../src/pwc_mcp_tools.js";
import { gatewayHeaders, type GatewayContext } from "../src/provider.js";
const gateway: GatewayContext = { url: "https://gateway.example/private", capability: "private-test-token", sessionId: "s", turnId: "t", turnClaim: { turnId: "t", workerId: "w", workerGeneration: "1", leaseGeneration: "2" } };

test("MCP discovery registers only the approved server-owned schemas and structured output", async () => {
  const registered: any[] = [];
  const calls: any[] = [];
  await createPwcMcpToolsExtension(gateway, async (url, init) => {
    assert.equal(url, "https://gateway.example/private/catalog-mcp");
    assert.deepEqual(init?.headers, { "Content-Type": "application/json", ...gatewayHeaders(gateway) });
    const body = JSON.parse(String(init?.body)); calls.push(body);
    return Response.json({ result: body.tool ? { structuredContent: { items: [1] } } : { tools: PWC_MCP_TOOLS.map(name => ({
      name, description: "Server description", annotations: { readOnlyHint: true },
      inputSchema: { type: "object", properties: { limit: { type: "integer", maximum: 25 } } },
    })) } });
  })({ registerTool: (tool: any) => registered.push(tool) } as never);
  assert.deepEqual(registered.map(t => t.name), PWC_MCP_TOOL_NAMES);
  assert.equal(registered[0].parameters.properties.limit.anyOf[0].maximum, 25);
  const result = await registered[0].execute("id", { limit: null, query: "VLA", enabled: false });
  assert.deepEqual(calls[1], { tool: "search_papers", arguments: { query: "VLA", enabled: false } });
  assert.equal(result.content[0].text, '{"items":[1]}');
});

test("optional fields accept null and required server fields remain required", () => {
  const schema: any = nullableOptionalFields({ type: "object", required: ["paper"], properties: { paper: { type: "string" }, cursor: { type: "string" } } });
  assert.deepEqual(schema.required, ["paper"]);
  assert.deepEqual(schema.properties.paper, { type: "string" });
  assert.deepEqual(schema.properties.cursor.anyOf[1], { type: "null" });
});

test("denial and MCP errors do not retry or expose error bodies", async () => {
  let calls = 0;
  await assert.rejects(requestPwcMcp(gateway, "read_paper", {}, undefined, async () => {
    calls++; return new Response("secret-token", { status: 403 });
  }), /^Error: PwC MCP request failed \(403\)\.$/u);
  assert.equal(calls, 1);
  await assert.rejects(requestPwcMcp(gateway, "read_paper", {}, undefined, async () =>
    Response.json({ result: { isError: true, content: [{ text: "secret" }] } })), /could not complete/u);
});

test("oversize streams are cancelled and abort signal reaches fetch", async () => {
  let cancelled = false;
  await assert.rejects(requestPwcMcp(gateway, undefined, {}, undefined, async () => new Response(new ReadableStream({
    start(c) { c.enqueue(new Uint8Array(1024 * 1024 + 1)); }, cancel() { cancelled = true; },
  }))), /too large/u);
  assert.equal(cancelled, true);
  const controller = new AbortController(); controller.abort();
  await assert.rejects(requestPwcMcp(gateway, undefined, {}, controller.signal, async (_url, init) => {
    init?.signal?.throwIfAborted(); throw new Error("unreachable");
  }), { name: "AbortError" });
});

test("incomplete discovery fails without registering tools", async () => {
  await assert.rejects(async () => createPwcMcpToolsExtension(gateway, async () => Response.json({ result: { tools: [] } }))({ registerTool() { throw new Error("unreachable"); } } as never), /incomplete/u);
});

test("MCP tools preserve shared search, call, and output budgets", async () => {
  const { PolicyController } = await import("../src/policy.js");
  const original = process.env.PWC_CHAT_PWC_MCP_ENABLED;
  process.env.PWC_CHAT_PWC_MCP_ENABLED = "true";
  try {
    const p = new PolicyController({ catalogEnabled: true, maximumCalls: 8, maximumRounds: 8,
      maximumDirectSearches: 1, maximumWebSearches: 1, maximumResultBytes: 100,
      maximumTurnOutputBytes: 300, bashTimeoutSeconds: 5 });
    assert.equal(p.authorize("a", "pwc_list_papers", { search: "VLA" }), undefined);
    const result = p.finish("a", "x".repeat(500));
    assert.ok(Buffer.byteLength(result.content[0]!.text) <= 100);
    assert.match(p.authorize("b", "bash", { command: "pwc search x" }) ?? "", /Answer now/iu);
    const { renderPrompt } = await import("../src/prompt.js");
    const prompt = await renderPrompt({ model: "test", hfUsername: "test", webSearchEnabled: false, readerMode: false,
      catalogToolsEnabled: true, source: "The available tools for a normal research turn are Bash, Read, and search_web." });
    assert.ok(prompt.includes("pwc_read_paper") && prompt.includes("pwc_search_papers"));
  } finally {
    if (original === undefined) delete process.env.PWC_CHAT_PWC_MCP_ENABLED;
    else process.env.PWC_CHAT_PWC_MCP_ENABLED = original;
  }
});

import assert from "node:assert/strict";
import test from "node:test";
import { CATALOG_TOOL_NAMES, createCatalogToolsExtension, requestCatalog } from "../src/catalog_tools.js";
import { gatewayHeaders, type GatewayContext } from "../src/provider.js";
import { PolicyController } from "../src/policy.js";
import { renderPrompt } from "../src/prompt.js";

const gateway: GatewayContext = {
  url: "https://gateway.example/api/internal/chat-gateway/",
  capability: "private-test-capability", sessionId: "session", turnId: "turn",
  turnClaim: { turnId: "turn", workerId: "worker", workerGeneration: "2", leaseGeneration: "3" },
};

test("catalog requests preserve all capability and durable ownership headers", async () => {
  const calls: { url: unknown; init: RequestInit | undefined }[] = [];
  for (const operation of ["search", "paper_info", "paper_list"] as const) {
    const result = await requestCatalog(gateway, operation, { query: "x; $(danger)" }, undefined, async (url, init) => {
      calls.push({ url, init });
      return Response.json({ result: { papers: [1] } });
    });
    assert.equal(result, '{"papers":[1]}');
    const last = calls.at(-1)!;
    assert.equal(last.url, "https://gateway.example/api/internal/chat-gateway/catalog");
    assert.deepEqual(last.init?.headers, { "Content-Type": "application/json", ...gatewayHeaders(gateway) });
    assert.deepEqual(JSON.parse(String(last.init?.body)), { operation, arguments: { query: "x; $(danger)" } });
    assert.equal(last.init?.redirect, "error");
  }
  assert.equal(calls.length, 3);
});

test("gateway denial is returned without retry or reflecting sensitive error bodies", async () => {
  let calls = 0;
  await assert.rejects(requestCatalog(gateway, "paper_info", { paper: "1" }, undefined, async () => {
    calls += 1;
    return new Response("private-test-capability", { status: 403 });
  }), /^Error: Catalog request failed \(403\)\.$/u);
  assert.equal(calls, 1);
});

test("unused filters are omitted while explicit false and meaningful filters survive", async () => {
  await requestCatalog(gateway, "paper_list", {
    page: null, page_size: 1, order_by: "date_published", task: "", method: null,
    start_date: null, end_date: null, all_versions: false, organization: "Google",
  }, undefined, async (_url, init) => {
    assert.deepEqual(JSON.parse(String(init?.body)), { operation: "paper_list", arguments: {
      page_size: 1, order_by: "date_published", all_versions: false, organization: "Google",
    } });
    return Response.json({ result: { papers: [] } });
  });
});

test("every optional catalog field accepts null for strict provider schemas", () => {
  const registered: { parameters: { required?: string[]; properties: Record<string, { anyOf?: { type?: string }[] }> } }[] = [];
  createCatalogToolsExtension(gateway)({ registerTool(tool: typeof registered[number]) { registered.push(tool); } } as never);
  for (const { parameters } of registered) {
    for (const [name, schema] of Object.entries(parameters.properties)) {
      if (!parameters.required?.includes(name)) {
        assert.ok(schema.anyOf?.some(branch => branch.type === "null"), name);
      }
    }
  }
});

test("catalog reads stop and cancel the stream at the byte bound", async () => {
  let cancelled = false;
  const response = new Response(new ReadableStream({
    start(controller) { controller.enqueue(new Uint8Array(1024 * 1024 + 1)); },
    cancel() { cancelled = true; },
  }));
  await assert.rejects(requestCatalog(gateway, "search", { query: "x" }, undefined, async () => response), /too large/u);
  assert.equal(cancelled, true);
});

test("catalog forwards cancellation and rejects malformed responses", async () => {
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(requestCatalog(gateway, "search", {}, controller.signal, async (_url, init) => {
    assert.equal(init?.signal?.aborted, true);
    init?.signal?.throwIfAborted();
    throw new Error("unreachable");
  }), { name: "AbortError" });
  for (const body of ["oops", "[]", "{}", "null"]) {
    await assert.rejects(requestCatalog(gateway, "paper_list", {}, undefined, async () => new Response(body)), /invalid/u);
  }
});

test("structured tool registration is lazy and exposes no credential or shell arguments", () => {
  const tools: { name: string; parameters: { properties: Record<string, unknown> } }[] = [];
  createCatalogToolsExtension(gateway)({ registerTool(tool: typeof tools[number]) { tools.push(tool); } } as never);
  assert.deepEqual(tools.map(t => t.name), CATALOG_TOOL_NAMES);
  for (const tool of tools) {
    for (const forbidden of ["capability", "gateway", "command", "operation", "url"]) {
      assert.equal(forbidden in tool.parameters.properties, false);
    }
  }
});

test("registered catalog tools execute the corresponding gateway operation", async (t) => {
  const calls: unknown[] = [];
  t.mock.method(globalThis, "fetch", async (_url: unknown, init: RequestInit) => {
    calls.push(JSON.parse(String(init.body)));
    return Response.json({ result: { title: "A paper" } });
  });
  const registered: { execute: (id: string, args: Record<string, unknown>, signal: AbortSignal) => Promise<unknown> }[] = [];
  createCatalogToolsExtension(gateway)({ registerTool(tool: typeof registered[number]) { registered.push(tool); } } as never);
  assert.equal(calls.length, 0);
  const args = [{ query: "attention" }, { paper: "1706.03762" }, { task: "image-classification", page_size: 5 }];
  for (const [i, tool] of registered.entries()) {
    assert.deepEqual(await tool.execute(`tool-${i}`, args[i]!, new AbortController().signal), {
      content: [{ type: "text", text: '{"title":"A paper"}' }], details: {},
    });
  }
  assert.deepEqual(calls, ["search", "paper_info", "paper_list"].map((operation, i) => ({ operation, arguments: args[i] })));
});

test("only the external catalog-enabled prompt advertises structured tools", async () => {
  const options = { model: "test", hfUsername: "test", webSearchEnabled: false, readerMode: false,
    source: "The available tools for a normal research turn are Bash, Read, and search_web." };
  assert.equal(await renderPrompt(options), options.source.replace("search_web", "mcp__exa__search_web"));
  const enabled = await renderPrompt({ ...options, catalogToolsEnabled: true });
  for (const name of CATALOG_TOOL_NAMES) assert.ok(enabled.includes(name));
  assert.match(enabled, /same search budget/u);
});

function policy(enabled: boolean) {
  return new PolicyController({ catalogEnabled: enabled, maximumCalls: 8, maximumRounds: 8,
    maximumDirectSearches: 1, maximumWebSearches: 1, maximumResultBytes: 100,
    maximumTurnOutputBytes: 300, bashTimeoutSeconds: 5 });
}

test("structured search shares the CLI search budget in both directions", () => {
  for (const directFirst of [true, false]) {
    const p = policy(true);
    const first = directFirst ? "pwc_search" : "bash";
    const second = directFirst ? "bash" : "pwc_search";
    assert.equal(p.authorize("a", first, { command: "pwc search x", query: "x" }), undefined);
    p.finish("a", "result");
    assert.match(p.authorize("b", second, { command: "pwc search y", query: "y" }) ?? "", /Answer now/iu);
    assert.equal(p.searches, 1);
  }
});

test("catalog tools require explicit availability and consume common call/output budgets", () => {
  for (const name of CATALOG_TOOL_NAMES) {
    assert.match(policy(false).authorize("a", name, {}) ?? "", /not available/u);
  }
  const p = policy(true);
  assert.equal(p.authorize("a", "pwc_paper_info", { paper: "1" }), undefined);
  assert.equal(p.calls, 1);
  assert.equal(p.searches, 0);
  const result = p.finish("a", "x".repeat(500));
  assert.ok(Buffer.byteLength(result.content[0]!.text) <= 100);
});

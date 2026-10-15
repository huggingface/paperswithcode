import assert from "node:assert/strict";
import test from "node:test";
import { SessionManager } from "@earendil-works/pi-coding-agent";
import { createPwcMcpToolsExtension, PWC_MCP_TOOLS } from "../src/pwc_mcp_tools.js";
import type { GatewayContext } from "../src/provider.js";

const gateway = { url: "https://gateway.example", capability: "test", sessionId: "s", turnId: "t", turnClaim: { turnId: "t", workerId: "w", workerGeneration: "1", leaseGeneration: "1" } } as GatewayContext;
async function reader(manager: SessionManager, respond: (args: any) => object) {
  const tools: any[] = [];
  const calls: any[] = [];
  await createPwcMcpToolsExtension(gateway, async (_url, init) => {
    const body = JSON.parse(String(init?.body));
    if (!body.tool) return Response.json({ result: { tools: PWC_MCP_TOOLS.map(name => ({
      name, description: "Research", annotations: { readOnlyHint: true },
      inputSchema: { type: "object", required: ["paper"], properties: { paper: { type: "string" }, cursor: { type: "string" } } },
    })) } });
    calls.push(body.arguments);
    return Response.json({ result: respond(body.arguments) });
  })({ registerTool: (tool: any) => tools.push(tool), appendEntry: (type: string, data: unknown) => manager.appendCustomEntry(type, data) } as never);
  const tool = tools.find(t => t.name === "pwc_read_paper");
  return { calls, tool, read: (paper: string, cursor?: string | null) => tool.execute("call", { paper, cursor }, undefined, undefined, { sessionManager: manager }) };
}

test("next-page requests forward the exact signed cursor without exposing it to the model", async () => {
  const manager = SessionManager.inMemory();
  const cursor = "signed.Abc+/=_-".repeat(30);
  const r = await reader(manager, args => ({ structuredContent: args.cursor ? { text: "page two", next_cursor: null } : { text: "page one", next_cursor: cursor } }));
  const first = await r.read("2506.01844");
  assert.deepEqual(JSON.parse(first.content[0].text), { next_cursor: "next", text: "page one" });
  assert.ok(!JSON.stringify(manager.buildSessionContext()).includes(cursor));
  assert.match(r.tool.parameters.properties.cursor.anyOf[0].description, /cursor: "next"/);
  assert.equal(JSON.parse((await r.read("2506.01844", "next")).content[0].text).next_cursor, null);
  assert.deepEqual(r.calls, [{ paper: "2506.01844" }, { paper: "2506.01844", cursor }]);
  await assert.rejects(r.read("2506.01844", "next"), /no next page/);
  assert.equal(r.calls.length, 2);
  await r.read("2506.01844", null);
  assert.equal(r.calls[2]!.cursor, undefined);
});

test("pagination survives session restore and follows the selected branch, not other papers or sessions", async () => {
  const manager = SessionManager.inMemory();
  const r = await reader(manager, args => ({ structuredContent: { next_cursor: `${args.paper}:${args.cursor ?? "first"}:signed` } }));
  await r.read("paper-a");
  const branch = manager.getLeafId()!;
  await r.read("paper-b");
  await r.read("paper-a", "next");
  const restored = SessionManager.inMemory(undefined, undefined, JSON.parse(JSON.stringify([manager.getHeader(), ...manager.getEntries()])));
  const resumed = await reader(restored, () => ({ structuredContent: { next_cursor: null } }));
  await resumed.read("paper-a", "next");
  assert.equal(resumed.calls[0].cursor, "paper-a:paper-a:first:signed:signed");
  restored.branch(branch);
  await resumed.read("paper-a", "next");
  assert.equal(resumed.calls[1].cursor, "paper-a:first:signed");
  await resumed.read("paper-b", "next");
  assert.equal(resumed.calls[2].cursor, undefined);
  const unrelated = await reader(SessionManager.inMemory(), () => ({ structuredContent: { next_cursor: null } }));
  await unrelated.read("paper-a", "next");
  assert.deepEqual(unrelated.calls, [{ paper: "paper-a" }]);
});

test("a first read with cursor next starts at the beginning and then pages on", async () => {
  // Production chat: 34 read_paper calls a week opened a paper with cursor
  // "next" and failed with "No saved page for this paper".
  const manager = SessionManager.inMemory();
  const r = await reader(manager, args => ({ structuredContent: { text: args.cursor ? "page two" : "page one", next_cursor: args.cursor ? null : "signed-two" } }));
  assert.deepEqual(JSON.parse((await r.read("2610.17552", "next")).content[0].text), { next_cursor: "next", text: "page one" });
  assert.equal(JSON.parse((await r.read("2610.17552", "next")).content[0].text).text, "page two");
  assert.deepEqual(r.calls, [{ paper: "2610.17552" }, { paper: "2610.17552", cursor: "signed-two" }]);
});

test("failed or expired continuation does not advance state; raw historical cursors still work", async () => {
  const manager = SessionManager.inMemory();
  let fail = true;
  const r = await reader(manager, args => {
    if (args.cursor && fail) return { isError: true, content: [{ text: "invalid continuation cursor; omit cursor to start from the beginning" }] };
    return { structuredContent: { next_cursor: "exact-signed-cursor" } };
  });
  await r.read("paper");
  const leaf = manager.getLeafId();
  await assert.rejects(r.read("paper", "next"), /omit cursor/);
  assert.equal(manager.getLeafId(), leaf);
  fail = false;
  await r.read("paper", "next");
  assert.equal(r.calls[2]!.cursor, "exact-signed-cursor");
  await r.read("paper", "historical-signed-cursor");
  assert.equal(r.calls[3].cursor, "historical-signed-cursor");
});

test("compaction preserves application pagination state outside model context", async () => {
  const manager = SessionManager.inMemory();
  manager.appendMessage({ role: "user", content: "Read a paper", timestamp: Date.now() });
  const r = await reader(manager, () => ({ structuredContent: { next_cursor: "retained-signed-token" } }));
  await r.read("paper");
  manager.appendCompaction("Read the first page; more remains.", null, 10000);
  assert.ok(!JSON.stringify(manager.buildSessionContext()).includes("retained-signed-token"));
  await r.read("paper", "next");
  assert.equal(r.calls[1].cursor, "retained-signed-token");
});

test("parallel next-page requests cannot skip a page or cross papers", async () => {
  const manager = SessionManager.inMemory();
  const r = await reader(manager, args => ({ structuredContent: { next_cursor: `${args.paper}:${args.cursor ?? "first"}:signed` } }));
  await r.read("a");
  await r.read("b");
  await Promise.all([r.read("a", "next"), r.read("a", "next"), r.read("b", "next")]);
  assert.deepEqual(r.calls.slice(2), [
    { paper: "a", cursor: "a:first:signed" },
    { paper: "a", cursor: "a:first:signed" },
    { paper: "b", cursor: "b:first:signed" },
  ]);
});

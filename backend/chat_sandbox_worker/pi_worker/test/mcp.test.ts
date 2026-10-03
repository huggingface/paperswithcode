import http from "node:http";
import { PolicyController, pwcExtension } from "../src/policy.js";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import {
  createAgentSession, DefaultResourceLoader, SessionManager, SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { createWebMcpExtension, WEB_SEARCH_TOOL, chatToolName } from "../src/mcp.js";
import { createProvider } from "../src/provider.js";

const tsx = new URL("../node_modules/tsx/dist/loader.mjs", import.meta.url).pathname;
const exaServer = new URL("../src/exa_mcp_server.ts", import.meta.url).pathname;

async function openSession(exa: boolean, exaEnv?: Record<string, string>, policy?: PolicyController) {
  const agentDir = await mkdtemp(path.join(tmpdir(), "pwc-pi-mcp-"));
  // Neither file may add servers to this worker, even when the workspace is trusted.
  const injected = JSON.stringify({ mcpServers: { unwanted: { command: process.execPath, args: ["--import", tsx, exaServer], exposure: "direct" } } });
  await writeFile(path.join(agentDir, "mcp.json"), injected);
  await mkdir(path.join(agentDir, ".pi"));
  await writeFile(path.join(agentDir, ".pi/mcp.json"), injected);
  const settings = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
  const loader = new DefaultResourceLoader({
    cwd: agentDir, agentDir, settingsManager: settings,
    noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true,
    systemPrompt: "PwC MCP test prompt\n",
    extensionFactories: [...(policy ? [pwcExtension(policy)] : []), { name: "pwc-mcp", factory: createWebMcpExtension(process.execPath, ["--import", tsx, exaServer], { exa, ...(exaEnv ? { exaEnv } : {}) }), hidden: true }],
  });
  await loader.reload();
  const provider = await createProvider("test-route");
  const created = await createAgentSession({
    cwd: agentDir, agentDir, modelRuntime: provider.runtime, model: provider.model,
    tools: [WEB_SEARCH_TOOL], resourceLoader: loader, settingsManager: settings,
    sessionManager: SessionManager.inMemory(agentDir),
  });
  await created.session.bindExtensions({ mode: "print" });
  // Native MCP discovers in the background; wait for the same pre-prompt hook
  // used by the real worker, without making a model request.
  await created.session.extensionRunner.emitBeforeAgentStart("test", undefined, { cwd: agentDir, sections: {} });
  created.extensionsResult.runtime.refreshTools();
  return { agentDir, created };
}

for (const enabled of [true, false]) {
  test(`native MCP exposes only gateway web search when enabled=${enabled}`, async () => {
    const { agentDir, created } = await openSession(enabled);
    try {
      assert.deepEqual(created.extensionsResult.errors, []);
      assert.deepEqual(created.session.getActiveToolNames(), enabled ? [WEB_SEARCH_TOOL] : []);
      assert.deepEqual(created.session.getAllTools().map(tool => tool.name), enabled ? [WEB_SEARCH_TOOL] : []);
      if (enabled) assert.match(created.session.getToolDefinition(WEB_SEARCH_TOOL)?.description ?? "", /trusted PwC Exa gateway/u);
    } finally {
      await created.session.extensionRunner.emit({ type: "session_shutdown", reason: "quit" });
      created.session.dispose();
      await rm(agentDir, { recursive: true, force: true });
    }
  });
}

test("native web search keeps the public tool name without aliasing arbitrary MCP servers", () => {
  assert.equal(chatToolName(WEB_SEARCH_TOOL), "search_web");
  assert.equal(chatToolName("mcp__untrusted__search_web"), "mcp__untrusted__search_web");
});

test("native MCP calls keep gateway fencing and enforce the shared web-search budget", async () => {
  const requests: { authorization: string | undefined; turn: string | undefined; body: unknown }[] = [];
  const server = http.createServer(async (request, response) => {
    const chunks: Buffer[] = [];
    for await (const chunk of request) chunks.push(Buffer.from(chunk));
    requests.push({ authorization: request.headers.authorization, turn: request.headers['x-pwc-turn'] as string, body: JSON.parse(Buffer.concat(chunks).toString()) });
    response.setHeader("Content-Type", "application/json");
    response.end(JSON.stringify({ result: { results: [{ title: "Native MCP evidence" }] } }));
  });
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as { port: number }).port;
  const policy = new PolicyController({ maximumCalls: 5, maximumRounds: 4, maximumDirectSearches: 1,
    maximumWebSearches: 1, maximumResultBytes: 1024, maximumTurnOutputBytes: 4096, bashTimeoutSeconds: 5 });
  policy.reset(true, "test");
  const { agentDir, created } = await openSession(true, {
    PWC_EXTERNAL_GATEWAY_URL: `http://127.0.0.1:${port}`,
    PWC_EXTERNAL_GATEWAY_CAPABILITY: "fixture-capability",
    PWC_EXTERNAL_GATEWAY_TURN: "fixture-turn",
  }, policy);
  try {
    const context = created.session.extensionRunner.createToolContext("parent", undefined);
    const allowed = await created.session.extensionRunner.emitToolCall({ type: "tool_call", toolCallId: "first", toolName: WEB_SEARCH_TOOL, input: { query: "Pi 1.0" } });
    assert.equal(allowed?.block, undefined);
    const definition = created.session.getToolDefinition(WEB_SEARCH_TOOL)!;
    const result = await definition.execute("first", { query: "Pi 1.0" }, undefined, undefined, context);
    assert.match(JSON.stringify(result), /Native MCP evidence/u);
    const blocked = await created.session.extensionRunner.emitToolCall({ type: "tool_call", toolCallId: "second", toolName: WEB_SEARCH_TOOL, input: { query: "another query" } });
    assert.equal(blocked?.block, true);
    assert.match(JSON.stringify(blocked), /answer now/iu);
    assert.equal(requests.length, 1);
    assert.deepEqual(requests[0], { authorization: "Bearer fixture-capability", turn: "fixture-turn", body: { operation: "web_search", arguments: { query: "Pi 1.0" } } });
  } finally {
    await created.session.extensionRunner.emit({ type: "session_shutdown", reason: "quit" });
    created.session.dispose();
    await rm(agentDir, { recursive: true, force: true });
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
});

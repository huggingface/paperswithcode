import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";
import {
  createAgentSession,
  createCodemodeExtension,
  DefaultResourceLoader,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { PiEventAdapter, type PwCEvent } from "../src/events.js";
import { PolicyController, pwcExtension, SCRIPT_BUDGET_SPENT } from "../src/policy.js";
import { createProvider } from "../src/provider.js";
import { CODEMODE_INLINE_BUDGET, CODEMODE_TOOL, createPwcMcpToolsExtension, PWC_MCP_TOOL_NAMES, PWC_MCP_TOOLS } from "../src/pwc_mcp_tools.js";

const usage = {
  input_tokens: 1,
  input_tokens_details: { cached_tokens: 0 },
  output_tokens: 1,
  output_tokens_details: { reasoning_tokens: 0 },
  total_tokens: 2,
};

function stream(events: Array<Record<string, unknown>>): string {
  return events.map((event) => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`).join("");
}

function toolCallResponse(name: string, args: string, sequence: number): string {
  const item = { id: `fc-${sequence}`, type: "function_call", status: "completed", call_id: `call-${sequence}`, name, arguments: args };
  const response = { id: `response-${sequence}`, status: "completed", output: [item], usage };
  return stream([
    { type: "response.created", response },
    { type: "response.output_item.added", output_index: 0, item: { ...item, arguments: "" } },
    { type: "response.function_call_arguments.delta", output_index: 0, item_id: item.id, delta: args },
    { type: "response.function_call_arguments.done", output_index: 0, item_id: item.id, arguments: args },
    { type: "response.output_item.done", output_index: 0, item },
    { type: "response.completed", response },
  ]);
}

function textResponse(text: string, sequence: number): string {
  const item = { id: `message-${sequence}`, type: "message", status: "completed", role: "assistant", content: [{ type: "output_text", text, annotations: [] }] };
  const response = { id: `response-${sequence}`, status: "completed", output: [item], usage };
  return stream([
    { type: "response.created", response },
    { type: "response.output_item.added", output_index: 0, item: { ...item, content: [] } },
    { type: "response.output_text.delta", output_index: 0, content_index: 0, delta: text },
    { type: "response.output_item.done", output_index: 0, item },
    { type: "response.completed", response },
  ]);
}

const SCRIPT = [
  "const [task, benchmarks] = await Promise.all([",
  "  tools.pwc_get_task({ name: 'image-classification' }),",
  "  tools.pwc_list_benchmarks({ task: 'image-classification' }),",
  "]);",
  "text({ task: task.slug, benchmarks: benchmarks.items.map((item) => item.slug) });",
].join("\n");

test("codemode scripts call the catalog tools, receive structured results, and report nested calls", async () => {
  const original = process.env.PWC_CHAT_PWC_MCP_ENABLED;
  process.env.PWC_CHAT_PWC_MCP_ENABLED = "true";
  const requests: Array<Record<string, any>> = [];
  const server = http.createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    request.on("end", () => {
      requests.push(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      response.writeHead(200, { "Content-Type": "text/event-stream" });
      response.end(requests.length === 1
        ? toolCallResponse(CODEMODE_TOOL, JSON.stringify({ code: SCRIPT }), 1)
        : textResponse("done", requests.length));
    });
  });
  await new Promise<void>((resolve, reject) => server.listen(0, "127.0.0.1", resolve).once("error", reject));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const gateway = {
    url: `http://127.0.0.1:${address.port}`,
    capability: "test-capability",
    sessionId: "10000000-0000-4000-8000-000000000001",
    turnId: "20000000-0000-4000-8000-000000000001",
    turnClaim: { turnId: "20000000-0000-4000-8000-000000000001", workerId: "test-worker", workerGeneration: 1, leaseGeneration: 1 },
  };
  const catalogCalls: Array<Record<string, unknown>> = [];
  const catalog = async (_url: string | URL | Request, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body));
    if (!body.tool) {
      return Response.json({ result: { tools: PWC_MCP_TOOLS.map((name) => ({
        name, description: `PwC ${name}`, annotations: { readOnlyHint: true },
        inputSchema: { type: "object", properties: { name: { type: "string" }, task: { type: "string" } } },
      })) } });
    }
    catalogCalls.push(body);
    return Response.json({ result: { structuredContent: body.tool === "get_task"
      ? { slug: "image-classification", description: "x".repeat(5_000) }
      : { items: [{ slug: "imagenet" }, { slug: "cifar-10" }] } } });
  };
  const policy = new PolicyController({ catalogEnabled: true, maximumCalls: 12, maximumRounds: 6,
    maximumDirectSearches: 4, maximumWebSearches: 2, maximumResultBytes: 2_000,
    maximumTurnOutputBytes: 20_000, bashTimeoutSeconds: 5 });
  policy.reset(false, "PwC test prompt");
  const provider = await createProvider("gpt-5.6-luna", "openai-responses", gateway);
  const settings = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
  const loader = new DefaultResourceLoader({
    cwd: "/workspace",
    agentDir: "/tmp/pwc-pi-test-codemode",
    settingsManager: settings,
    noExtensions: true,
    noSkills: true,
    noPromptTemplates: true,
    noThemes: true,
    noContextFiles: true,
    systemPrompt: "PwC test prompt",
    extensionFactories: [
      { name: "pwc-policy", factory: pwcExtension(policy) },
      { name: "pwc-catalog", factory: createPwcMcpToolsExtension(gateway, catalog as typeof fetch, undefined, { codemode: true }) },
      { name: "pwc-codemode", factory: createCodemodeExtension({ mode: "on", models: false, inlineBudget: CODEMODE_INLINE_BUDGET }) },
    ],
  });
  await loader.reload();
  const { session, extensionsResult } = await createAgentSession({
    cwd: "/workspace",
    modelRuntime: provider.runtime,
    model: provider.model,
    tools: [CODEMODE_TOOL, ...PWC_MCP_TOOL_NAMES],
    resourceLoader: loader,
    settingsManager: settings,
    sessionManager: SessionManager.inMemory("/workspace"),
  });
  await session.bindExtensions({ mode: "print" });
  extensionsResult.runtime.refreshTools();
  session.setActiveToolsByName([CODEMODE_TOOL]);
  const adapter = new PiEventAdapter(false);
  const events: PwCEvent[] = [];
  const unsubscribe = session.subscribe((event) => events.push(...adapter.feed(event)));
  try {
    await session.prompt("Which benchmarks does image classification have?");

    const declared = (requests[0]!.tools as Array<{ name: string; description: string }>);
    assert.deepEqual(declared.map((tool) => tool.name), [CODEMODE_TOOL]);
    for (const name of PWC_MCP_TOOL_NAMES) assert.match(declared[0]!.description, new RegExp(`${name}\\(args`, "u"));
    assert.deepEqual(catalogCalls.map((call) => call.tool).sort(), ["get_task", "list_benchmarks"]);
    const scriptOutput = JSON.stringify(requests[1]!.input);
    assert.match(scriptOutput, /\\"task\\":\\"image-classification\\"/u);
    assert.match(scriptOutput, /imagenet/u);
    assert.doesNotMatch(scriptOutput, /xxxxxxxxxx/u, "only the script's output reaches the model");
    assert.equal(policy.calls, 1, "the script is one model-issued call");
    assert.equal(policy.scriptCalls, 2, "its catalog calls spend the script budget");
    assert.ok(policy.scriptBytes > 5_000, "script result bytes are counted from the full results");

    const starts = events.filter((event) => event.type === "tool_call_start");
    const script = starts.find((event) => event.name === CODEMODE_TOOL);
    assert.ok(script);
    const nested = starts.filter((event) => event.name !== CODEMODE_TOOL);
    assert.deepEqual(nested.map((event) => event.name).sort(), ["pwc_get_task", "pwc_list_benchmarks"]);
    assert.ok(nested.every((event) => event.parent_id === script.id));
    const results = events.filter((event) => event.type === "tool_result");
    assert.equal(results.length, 3);
    assert.ok(results.every((event) => event.status === "success"));
  } finally {
    unsubscribe();
    session.dispose();
    await new Promise<void>((resolve) => server.close(() => resolve()));
    if (original === undefined) delete process.env.PWC_CHAT_PWC_MCP_ENABLED;
    else process.env.PWC_CHAT_PWC_MCP_ENABLED = original;
  }
});

test("run frames carry the optional codemode_enabled flag", async () => {
  const { parseRunTurn } = await import("../src/turn_protocol.js");
  const frame = {
    v: 1, type: "run_turn", request_id: "r", chat_session_id: "s", prompt: "hi", model: "m",
    resume: null, web_search_enabled: false, reasoning_effort: "low", fetchable_urls: [],
    hf_username: "u", agent_harness: "pi",
  };
  assert.equal(parseRunTurn(frame).codemode_enabled, false);
  assert.equal(parseRunTurn({ ...frame, codemode_enabled: true }).codemode_enabled, true);
  assert.throws(() => parseRunTurn({ ...frame, codemode_enabled: "yes" }), /Invalid Pi run frame value/u);
});

test("codemode research prompts route the catalog tools through scripts", async () => {
  const { renderMcpResearchPrompt } = await import("../src/mcp_research_prompt.js");
  const source = "The available tools for a normal research turn are Bash, Read, and search_web.\n<cli_usage>x</cli_usage>";
  const direct = renderMcpResearchPrompt(source, "skill");
  const scripted = renderMcpResearchPrompt(source, "skill", { codemode: true });
  assert.doesNotMatch(direct, /codemode/u);
  assert.match(scripted, /The available tools for a normal research turn are search_web and codemode\. Call the PwC MCP tools \(pwc_search_papers/u);
  assert.match(scripted, /<codemode_usage>[\s\S]*Promise\.allSettled[\s\S]*<\/codemode_usage>/u);
  const authoring = renderMcpResearchPrompt(source, "skill", { codemode: true, sandboxTools: true });
  assert.doesNotMatch(authoring, /codemode/u);
});

test("scripts spend their own catalog budget while each script spends one call and round", () => {
  const original = process.env.PWC_CHAT_PWC_MCP_ENABLED;
  process.env.PWC_CHAT_PWC_MCP_ENABLED = "true";
  try {
    const policy = new PolicyController({ catalogEnabled: true, maximumCalls: 2, maximumRounds: 4,
      maximumDirectSearches: 1, maximumWebSearches: 1, maximumResultBytes: 50,
      maximumTurnOutputBytes: 100, bashTimeoutSeconds: 5, scriptMaximumCatalogCalls: 3, scriptMaximumCatalogBytes: 1_000 });
    policy.reset(false, "prompt");
    assert.equal(policy.authorize("s", CODEMODE_TOOL, { code: "" }), undefined);
    assert.equal(policy.authorize("s/1", "pwc_get_task", { task: "a" }, true), undefined);
    assert.equal(policy.authorize("s/2", "pwc_get_task", { task: "b" }, true), undefined);
    assert.equal(policy.authorize("s/3", "pwc_search_papers", { query: "a" }, true), undefined);
    assert.equal(policy.rounds, 1);
    assert.equal(policy.calls, 1, "the script itself is one call; its catalog calls are not");
    assert.equal(policy.scriptCalls, 3);
    assert.equal(policy.authorize("s/4", "pwc_get_task", { task: "c" }, true), SCRIPT_BUDGET_SPENT);
    assert.equal(policy.toolingClosed, false, "a spent script budget leaves the other tools open");
    for (const id of ["s/1", "s/2", "s/3"]) policy.finishNested(id, [{ type: "text", text: "x".repeat(200) }], false);
    assert.equal(policy.scriptBytes, 600);
    assert.equal(policy.outputBytes, 0, "script results never reach the model");
    assert.ok(Buffer.byteLength(policy.finish("s", "x".repeat(500)).content[0]!.text) <= 50);
  } finally {
    if (original === undefined) delete process.env.PWC_CHAT_PWC_MCP_ENABLED;
    else process.env.PWC_CHAT_PWC_MCP_ENABLED = original;
  }
});

test("script result bytes and the search ceiling also bound scripts", () => {
  const original = process.env.PWC_CHAT_PWC_MCP_ENABLED;
  process.env.PWC_CHAT_PWC_MCP_ENABLED = "true";
  try {
    const policy = new PolicyController({ catalogEnabled: true, maximumCalls: 12, maximumRounds: 6,
      maximumDirectSearches: 1, maximumWebSearches: 1, maximumResultBytes: 50,
      maximumTurnOutputBytes: 100, bashTimeoutSeconds: 5, scriptMaximumCatalogBytes: 1_000 });
    policy.reset(false, "prompt");
    policy.authorize("s", CODEMODE_TOOL, { code: "" });
    assert.equal(policy.authorize("s/1", "pwc_search_papers", { query: "a" }, true), undefined);
    assert.match(policy.authorize("s/2", "pwc_search_papers", { query: "b" }, true) ?? "", /Answer now/iu);

    policy.reset(true, "prompt");
    policy.authorize("t", CODEMODE_TOOL, { code: "" });
    assert.equal(policy.authorize("t/1", "pwc_get_task", { task: "a" }, true), undefined);
    policy.finishNested("t/1", [{ type: "text", text: "x".repeat(1_000) }], false);
    assert.equal(policy.authorize("t/2", "pwc_get_task", { task: "b" }, true), SCRIPT_BUDGET_SPENT);
    policy.finish("t", "done");
    assert.equal(policy.authorize("u", CODEMODE_TOOL, { code: "" }), SCRIPT_BUDGET_SPENT);
    assert.equal(policy.authorize("v", "search_web", { query: "q" }), undefined, "other tools keep their own budgets");
  } finally {
    if (original === undefined) delete process.env.PWC_CHAT_PWC_MCP_ENABLED;
    else process.env.PWC_CHAT_PWC_MCP_ENABLED = original;
  }
});

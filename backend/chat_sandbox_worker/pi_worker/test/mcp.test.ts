import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import {
  createAgentSession,
  DefaultResourceLoader,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { type McpStatusSnapshot } from "pi-mcp-adapter";
import { createViewResult } from "../src/excalidraw_view_mcp_server.js";
import { createWebMcpExtension, mcpDirectToolsList } from "../src/mcp.js";
import { assessExcalidrawReadiness } from "../src/mcp_app_registry.js";
import { createProvider } from "../src/provider.js";

const tsx = new URL("../node_modules/tsx/dist/loader.mjs", import.meta.url).pathname;
const exaServer = new URL("../src/exa_mcp_server.ts", import.meta.url).pathname;
const excalidrawFixture = new URL("./fixtures/excalidraw_mcp_server.ts", import.meta.url).pathname;
const excalidrawView = new URL("../src/excalidraw_view_mcp_server.ts", import.meta.url).pathname;

async function openSession(options: {
  tools: string[];
  exa?: boolean;
  excalidraw?: { command: string; args: string[] } | { url: string } | false;
}) {
  const agentDir = await mkdtemp(path.join(tmpdir(), "pwc-pi-mcp-"));
  process.env.PI_CODING_AGENT_DIR = agentDir;
  const settings = SettingsManager.inMemory({
    compaction: { enabled: false },
    retry: { enabled: false },
  });
  let status: McpStatusSnapshot | undefined;
  const waitingForView = Boolean(options.excalidraw && "url" in options.excalidraw);
  const loader = new DefaultResourceLoader({
    cwd: process.cwd(),
    agentDir,
    settingsManager: settings,
    noExtensions: true,
    noSkills: true,
    noPromptTemplates: true,
    noThemes: true,
    noContextFiles: true,
    systemPrompt: "PwC MCP test prompt\n",
    extensionFactories: [
      {
        name: "pwc-exa-mcp",
        factory: createWebMcpExtension(
          process.execPath,
          ["--import", tsx, exaServer],
          {
            exa: options.exa ?? true,
            excalidraw: options.excalidraw ?? false,
            ...(waitingForView
              ? { excalidrawView: { command: process.execPath, args: ["--import", tsx, excalidrawView] } }
              : {}),
            onStatus: (snapshot) => {
              status = snapshot;
            },
          },
        ),
        hidden: true,
      },
    ],
  });
  await loader.reload();
  const provider = await createProvider("test-route");
  const created = await createAgentSession({
    cwd: process.cwd(),
    modelRuntime: provider.runtime,
    model: provider.model,
    tools: options.tools,
    resourceLoader: loader,
    settingsManager: settings,
    sessionManager: SessionManager.inMemory(process.cwd()),
  });
  await created.session.bindExtensions({ mode: "print" });
  created.extensionsResult.runtime.refreshTools();
  const deadline = Date.now() + 8_000;
  while (options.excalidraw && Date.now() < deadline) {
    const server = status?.servers.find((entry) => entry.name === "excalidraw");
    const view = status?.servers.find((entry) => entry.name === "excalidraw_view");
    if (
      server
      && server.status !== "not-connected"
      && (!waitingForView || (view && view.status !== "not-connected"))
    ) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
    created.extensionsResult.runtime.refreshTools();
  }
  return { agentDir, created, status };
}

test("Pi exposes only the capability-backed Exa MCP search tool", async () => {
  const { agentDir, created } = await openSession({ tools: ["search_web"], excalidraw: false });
  try {
    assert.deepEqual(created.session.getActiveToolNames(), ["search_web"]);
    assert.deepEqual(created.session.getAllTools().map((tool) => tool.name), ["search_web"]);
    assert.match(
      created.session.getToolDefinition("search_web")?.description ?? "",
      /trusted PwC Exa gateway/u,
    );
  } finally {
    await created.session.extensionRunner.emit({ type: "session_shutdown", reason: "quit" });
    created.session.dispose();
    await rm(agentDir, { recursive: true, force: true });
  }
});

test("Pi does not start or expose Exa when web search is disabled", async () => {
  const { agentDir, created, status } = await openSession({
    tools: ["search_web"],
    exa: false,
    excalidraw: false,
  });
  try {
    assert.deepEqual(created.session.getActiveToolNames(), []);
    assert.deepEqual(created.session.getAllTools().map((tool) => tool.name), []);
    assert.equal(status?.servers.some((entry) => entry.name === "exa"), false);
    assert.deepEqual(mcpDirectToolsList(false, false), []);
  } finally {
    await created.session.extensionRunner.emit({ type: "session_shutdown", reason: "quit" });
    created.session.dispose();
    await rm(agentDir, { recursive: true, force: true });
  }
});

test("successful Excalidraw discovery registers only model-visible tools", async () => {
  const { agentDir, created, status } = await openSession({
    tools: ["read", "bash", "search_web", "read_me", "create_view"],
    excalidraw: { command: process.execPath, args: ["--import", tsx, excalidrawFixture] },
  });
  try {
    created.extensionsResult.runtime.refreshTools();
    const names = created.session.getActiveToolNames().sort();
    assert.ok(names.includes("read_me"));
    assert.ok(names.includes("create_view"));
    assert.ok(names.includes("search_web"));
    assert.ok(names.includes("read"));
    assert.ok(names.includes("bash"));
    assert.equal(names.includes("save_checkpoint"), false);
    assert.equal(names.includes("export_to_excalidraw"), false);
    const snapshot = assessExcalidrawReadiness({
      enabled: true,
      serverStatus: status?.servers.find((entry) => entry.name === "excalidraw")?.status,
      activeTools: names,
      createViewDefinition: created.session.getToolDefinition("create_view") as { parameters?: unknown } | undefined,
    });
    assert.equal(snapshot.ready, true);
    assert.match(created.session.getToolDefinition("read_me")?.description ?? "", /Excalidraw/u);
  } finally {
    await created.session.extensionRunner.emit({ type: "session_shutdown", reason: "quit" });
    created.session.dispose();
    await rm(agentDir, { recursive: true, force: true });
  }
});

test("Excalidraw connection failure omits the tools and keeps local research tools", async () => {
  const { agentDir, created, status } = await openSession({
    tools: ["read", "bash", "search_web", "read_me", "create_view"],
    excalidraw: { url: "https://127.0.0.1:1/mcp" },
  });
  try {
    created.extensionsResult.runtime.refreshTools();
    const names = created.session.getActiveToolNames();
    assert.ok(names.includes("create_view"));
    assert.equal(names.includes("read_me"), false);
    assert.equal(status?.servers.find((entry) => entry.name === "excalidraw_view")?.status, "connected");
    const definition = created.session.getToolDefinition("create_view") as { parameters?: { properties?: Record<string, unknown> } } | undefined;
    assert.ok(definition?.parameters?.properties && "elements" in definition.parameters.properties);
    created.session.setActiveToolsByName(names.filter((name) => name !== "read_me" && name !== "create_view"));
    created.extensionsResult.runtime.refreshTools();
    created.session.setActiveToolsByName(
      created.session.getActiveToolNames().filter((name) => name !== "read_me" && name !== "create_view"),
    );
    const active = created.session.getActiveToolNames().sort();
    assert.deepEqual(active.filter((name) => name === "read_me" || name === "create_view"), []);
    assert.ok(active.includes("search_web"));
    assert.ok(active.includes("read"));
    assert.ok(active.includes("bash"));
    const snapshot = assessExcalidrawReadiness({
      enabled: true,
      serverStatus: status?.servers.find((entry) => entry.name === "excalidraw")?.status ?? "failed",
      activeTools: active,
    });
    assert.equal(snapshot.ready, false);
    assert.ok(snapshot.failure_class);
  } finally {
    await created.session.extensionRunner.emit({ type: "session_shutdown", reason: "quit" });
    created.session.dispose();
    await rm(agentDir, { recursive: true, force: true });
  }
});

test("a mismatched metadata cache cannot mark Excalidraw ready", async () => {
  const snapshot = assessExcalidrawReadiness({
    enabled: true,
    serverStatus: "cached",
    activeTools: ["create_view", "read_me", "search_web"],
    createViewDefinition: { parameters: { type: "object", properties: { elements: { type: "string" } } } },
  });
  assert.equal(snapshot.ready, false);
  assert.equal(snapshot.failure_class, "configured_not_connected");
});

test("URL Excalidraw keeps create_view on a local ack server", () => {
  assert.deepEqual(mcpDirectToolsList(false), ["exa/search_web"]);
  assert.deepEqual(
    mcpDirectToolsList({ url: "https://mcp.excalidraw.com/mcp" }),
    ["exa/search_web", "excalidraw/read_me", "excalidraw_view/create_view"],
  );
  assert.deepEqual(
    mcpDirectToolsList({ command: "node", args: ["fixture.js"] }),
    ["exa/search_web", "excalidraw/read_me", "excalidraw/create_view"],
  );
});

test("local create_view acks valid scenes and errors on malformed JSON", () => {
  const ok = createViewResult([{ type: "rectangle", id: "n1" }]);
  assert.equal(ok.isError, undefined);
  assert.match(ok.content[0]?.text ?? "", /Diagram displayed/u);
  const bad = createViewResult('[{"type":"arrow","label":{"text":"draft tokens"}}},]');
  assert.equal(bad.isError, true);
  assert.match(bad.content[0]?.text ?? "", /Fix the JSON/u);
});

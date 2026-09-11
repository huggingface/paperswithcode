import { mkdirSync } from "node:fs";
import { createAgentSession, DefaultResourceLoader, SessionManager, SettingsManager } from "@earendil-works/pi-coding-agent";
import {
  createNativeExcalidrawExtension,
  loadExcalidrawReadMe,
} from "./excalidraw_tools.js";
import {
  EXCALIDRAW_APP_TOOLS,
  EXCALIDRAW_MODEL_TOOLS,
  assessExcalidrawReadiness,
} from "./mcp_app_registry.js";
import { createProvider } from "./provider.js";

process.env.MCP_UI_VIEWER = "none";
process.env.PWC_CHAT_EXCALIDRAW_ENABLED = "true";

const agentDir = "/tmp/pwc-qualify-pi";
mkdirSync(agentDir, { recursive: true });
process.env.PI_CODING_AGENT_DIR = agentDir;

const started = performance.now();

const settings = SettingsManager.inMemory({
  compaction: { enabled: false },
  retry: { enabled: false },
});
const loader = new DefaultResourceLoader({
  cwd: "/workspace",
  agentDir,
  settingsManager: settings,
  noExtensions: true,
  noSkills: true,
  noPromptTemplates: true,
  noThemes: true,
  noContextFiles: true,
  systemPrompt: "qualify\n",
  extensionFactories: [{
    name: "pwc-excalidraw",
    factory: createNativeExcalidrawExtension(),
    hidden: true,
  }],
});
await loader.reload();
const provider = await createProvider("qualify-route");
const created = await createAgentSession({
  cwd: "/workspace",
  agentDir,
  modelRuntime: provider.runtime,
  model: provider.model,
  tools: ["read", "bash", "search_web", ...EXCALIDRAW_MODEL_TOOLS],
  resourceLoader: loader,
  settingsManager: settings,
  sessionManager: SessionManager.inMemory("/workspace"),
});
try {
  await created.session.bindExtensions({ mode: "print" });
  created.extensionsResult.runtime.refreshTools();
  const names = created.session.getActiveToolNames();
  const registrationLatencyMs = Math.round(performance.now() - started);
  let readMeOk = false;
  try {
    readMeOk = (await loadExcalidrawReadMe()).trim().length > 0;
  } catch {
    readMeOk = false;
  }
  const snapshot = assessExcalidrawReadiness({
    enabled: true,
    serverStatus: readMeOk ? "connected" : "failed",
    activeTools: names,
    createViewDefinition: created.session.getToolDefinition("create_view") as { parameters?: unknown } | undefined,
    latencyMs: registrationLatencyMs,
  });
  const unexpected = names.filter((name) => (EXCALIDRAW_APP_TOOLS as readonly string[]).includes(name));
  process.stdout.write(`${JSON.stringify({
    ready: snapshot.ready && readMeOk && unexpected.length === 0,
    failure_class: unexpected.length ? "connected_incompatible" : snapshot.failure_class,
    registered_tool_names: snapshot.registered_tool_names,
    registered_tool_digest: snapshot.registered_tool_digest,
    registration_latency_ms: snapshot.registration_latency_ms,
    read_me_ok: readMeOk,
    server_status: readMeOk ? "connected" : "failed",
    server_tool_count: readMeOk ? 1 : 0,
  })}\n`);
  process.exitCode = snapshot.ready && readMeOk && unexpected.length === 0 ? 0 : 1;
} finally {
  await created.session.extensionRunner.emit({ type: "session_shutdown", reason: "quit" });
  created.session.dispose();
}

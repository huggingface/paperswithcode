import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";

import { createExternalWorkerServer } from "./external_server.js";
import { prewarmExternalWorkerAndListen } from "./external_startup.js";
import { PiWorker } from "./agent.js";
import { RemoteToolBridge } from "./external_tools.js";

const host = process.env.PWC_EXTERNAL_PI_HOST ?? "127.0.0.1";
const port = Number(process.env.PWC_EXTERNAL_PI_PORT ?? "8766");
const token = process.env.PWC_EXTERNAL_PI_TOKEN
  ?? process.env.PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN
  ?? "";
const maximumConcurrent = Number(
  process.env.PWC_EXTERNAL_PI_MAX_SESSIONS
    ?? process.env.PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS
    ?? "8",
);
const workerId = process.env.PWC_EXTERNAL_PI_WORKER_ID ?? "";
const instanceId = process.env.PWC_EXTERNAL_PI_INSTANCE_ID ?? randomUUID();
const releaseId = process.env.PWC_EXTERNAL_PI_RELEASE_ID
  ?? process.env.PWC_RELEASE_ID
  ?? "";
const promptPath = process.env.PWC_EXTERNAL_PI_PROMPT_PATH ?? "";
const toolNamesValue = process.env.PWC_EXTERNAL_PI_TOOL_NAMES ?? "";

if (host !== "127.0.0.1" && host !== "::1") {
  throw new Error("External shadow worker must bind to loopback");
}
if (!Number.isInteger(port) || port < 1 || port > 65_535) {
  throw new Error("External shadow worker port is invalid");
}

if (!promptPath) throw new Error("External shadow worker prompt path is missing");
const toolNames = JSON.parse(toolNamesValue) as unknown;
if (!Array.isArray(toolNames) || toolNames.some((name) => typeof name !== "string")) {
  throw new Error("External shadow worker tool profile is invalid");
}
const profile = { prompt: readFileSync(promptPath, "utf8"), tool_names: toolNames };

const server = createExternalWorkerServer({
  token,
  maximumConcurrent,
  workerId,
  instanceId,
  releaseId,
  profile,
  capabilityEvidence: {
    provider_credentials_present: [
      "OPENAI_API_KEY", "PWC_OPENAI_API_KEY", "PWC_OPENROUTER_API_KEY",
      "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
    ].some((key) => Boolean(process.env[key])),
    modal_credentials_present: Boolean(
      process.env.MODAL_TOKEN_ID || process.env.MODAL_TOKEN_SECRET,
    ),
  },
  createTurnWorker: (emit, run, channel) => new PiWorker(
    emit,
    {
      url: run.gateway_url,
      capability: run.capability,
      sessionId: run.chat_session_id,
      turnId: run.turn_id,
      turnClaim: run.turnClaim,
    },
    new RemoteToolBridge(channel),
    { excalidrawAvailable: run.excalidraw_enabled },
  ),
});

await prewarmExternalWorkerAndListen({
  maximumConcurrent,
  profile,
  listen: () => server.listen(port, host),
});

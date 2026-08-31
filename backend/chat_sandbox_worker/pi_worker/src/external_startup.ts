import {
  type ExternalShadowRequest,
  type ExternalWorkerProfile,
  MAX_EXTERNAL_SHADOW_TRANSCRIPT_ENTRIES,
  projectShadowState,
} from "./external_shadow.js";
import { handleExternalFrame } from "./external_worker.js";

type PrewarmFrameHandler = (
  frame: unknown,
  profile: ExternalWorkerProfile,
  ordinal: number,
) => Promise<unknown>;

interface ExternalWorkerPrewarmOptions {
  maximumConcurrent: number;
  profile: ExternalWorkerProfile;
  handleFrame?: PrewarmFrameHandler;
}

interface ExternalWorkerStartupOptions extends ExternalWorkerPrewarmOptions {
  listen: () => void;
}

function syntheticUuid(prefix: number, ordinal: number): string {
  return `${prefix.toString(16).padStart(8, "0")}-0000-4000-8000-${ordinal
    .toString(16).padStart(12, "0")}`;
}

function prewarmFrame(
  ordinal: number,
  profile: ExternalWorkerProfile,
): Record<string, unknown> {
  const agentSessionId = syntheticUuid(0x70000000, ordinal + 1);
  const entries: Record<string, unknown>[] = [{
    type: "session",
    id: agentSessionId,
    version: 3,
  }];
  let parentId: string | null = null;
  for (let index = 1; index < MAX_EXTERNAL_SHADOW_TRANSCRIPT_ENTRIES; index += 1) {
    const id = `prewarm-${ordinal}-${index}`;
    entries.push({ type: "message", id, parentId, role: "user" });
    parentId = id;
  }
  const request: ExternalShadowRequest = {
    protocol_version: 1,
    request_id: `startup-prewarm-${ordinal}`,
    chat_session_id: syntheticUuid(0x60000000, ordinal + 1),
    agent_session_id: agentSessionId,
    current_leaf_id: parentId,
    expected_prompt_sha256: "0".repeat(64),
    expected_tool_names_sha256: "0".repeat(64),
    expected_transcript_sha256: "0".repeat(64),
    transcript_entries: entries,
  };
  const projection = projectShadowState(request, profile);
  return {
    type: "shadow_compare",
    ...request,
    expected_prompt_sha256: projection.prompt_sha256,
    expected_tool_names_sha256: projection.tool_names_sha256,
    expected_transcript_sha256: projection.transcript_sha256,
  };
}

export async function prewarmExternalWorker(
  options: ExternalWorkerPrewarmOptions,
): Promise<void> {
  const handler = options.handleFrame ?? handleExternalFrame;
  const invocations = Array.from({ length: options.maximumConcurrent }, (_, ordinal) => {
    const frame = prewarmFrame(ordinal, options.profile);
    return handler(frame, options.profile, ordinal);
  });
  const outcomes = await Promise.allSettled(invocations);
  if (outcomes.some((outcome) => outcome.status === "rejected")) {
    throw new Error("External worker startup prewarm failed");
  }
}

export async function prewarmExternalWorkerAndListen(
  options: ExternalWorkerStartupOptions,
): Promise<void> {
  await prewarmExternalWorker(options);
  options.listen();
}

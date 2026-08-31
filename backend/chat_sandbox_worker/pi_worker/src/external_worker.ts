import {
  projectShadowState,
  restoreShadowTranscript,
  type ExternalShadowRequest,
  type ExternalShadowProjection,
  type ExternalWorkerProfile,
} from "./external_shadow.js";

export const EXTERNAL_WORKER_PREFIX = "@@PWC_EXTERNAL_PI_V1@@";
export const MAX_EXTERNAL_FRAME_BYTES = 28 * 1024 * 1024;

export interface ExternalShadowFrame extends ExternalShadowRequest {
  type: "shadow_compare";
}

export interface ExternalShadowResult extends ExternalShadowProjection {
  type: "shadow_projection";
}

export async function handleExternalFrame(
  frame: unknown,
  profile: ExternalWorkerProfile,
): Promise<ExternalShadowResult> {
  if (!frame || typeof frame !== "object" || Array.isArray(frame)) {
    throw new Error("External worker frame must be a shadow_compare object");
  }
  const value = frame as Record<string, unknown>;
  if (value.type !== "shadow_compare") {
    throw new Error("External worker accepts only shadow_compare frames");
  }
  const keys = new Set([
    "type", "protocol_version", "request_id", "chat_session_id", "agent_session_id",
    "current_leaf_id", "expected_prompt_sha256", "expected_tool_names_sha256",
    "expected_transcript_sha256",
    "transcript_entries",
  ]);
  if (Object.keys(value).length !== keys.size || Object.keys(value).some((key) => !keys.has(key))) {
    throw new Error("External worker shadow_compare keys are invalid");
  }
  const { type: _type, ...request } = value;
  const shadowRequest = request as unknown as ExternalShadowFrame;
  await restoreShadowTranscript(shadowRequest);
  const projection = projectShadowState(shadowRequest, profile);
  return { type: "shadow_projection", ...projection };
}

export function encodeExternalFrame(frame: object): string {
  const payload = JSON.stringify(frame);
  if (Buffer.byteLength(payload) > MAX_EXTERNAL_FRAME_BYTES) {
    throw new Error("External worker response is too large");
  }
  return `${EXTERNAL_WORKER_PREFIX}${payload}\n`;
}

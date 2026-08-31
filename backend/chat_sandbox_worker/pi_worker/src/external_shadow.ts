import { createHash } from "node:crypto";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { SessionManager } from "@earendil-works/pi-coding-agent";
import { toolNameDigest } from "./mcp_app_registry.js";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const MAX_PROMPT_BYTES = 2 * 1024 * 1024;
export const MAX_EXTERNAL_SHADOW_TRANSCRIPT_ENTRIES = 2_000;
const MAX_TRANSCRIPT_BYTES = 25 * 1024 * 1024;
const MAX_TOOL_NAMES = 128;

export interface ExternalShadowRequest {
  protocol_version: 1;
  request_id: string;
  chat_session_id: string;
  agent_session_id: string;
  current_leaf_id: string | null;
  expected_prompt_sha256: string;
  expected_tool_names_sha256: string;
  expected_transcript_sha256: string;
  transcript_entries: Record<string, unknown>[];
}

export interface ExternalWorkerProfile {
  prompt: string;
  tool_names: string[];
}

export interface ExternalShadowProjection {
  protocol_version: 1;
  request_id: string;
  chat_session_id: string;
  agent_session_id: string;
  current_leaf_id: string | null;
  entry_count: number;
  transcript_sha256: string;
  prompt_sha256: string;
  tool_names_sha256: string;
}

export interface ExternalShadowComparison {
  compatible: boolean;
  mismatches: string[];
}

export interface RestoredShadowTranscript {
  agent_session_id: string;
  current_leaf_id: string | null;
  entry_count: number;
}

function sha256(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function canonicalJson(value: unknown): string {
  if (value === null) return '["null"]';
  if (typeof value === "string") return `["string",${JSON.stringify(value)}]`;
  if (typeof value === "boolean") return `["boolean",${JSON.stringify(value)}]`;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("External shadow transcript JSON is invalid");
    if (Number.isInteger(value) && !Number.isSafeInteger(value)) {
      throw new Error("External shadow transcript integer is unsafe");
    }
    const bytes = Buffer.allocUnsafe(8);
    bytes.writeDoubleBE(value);
    return `["number","${bytes.toString("hex")}"]`;
  }
  if (Array.isArray(value)) return `["array",[${value.map(canonicalJson).join(",")}]]`;
  if (value && typeof value === "object") {
    return `["object",[${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => Buffer.compare(Buffer.from(left), Buffer.from(right)))
      .map(([key, item]) => `[${JSON.stringify(key)},${canonicalJson(item)}]`).join(",")}]]`;
  }
  throw new Error("External shadow transcript JSON is invalid");
}

export function nativeJsonlTranscriptDigest(entries: Record<string, unknown>[]): string {
  return sha256(entries.map((entry) => `${canonicalJson(entry)}\n`).join(""));
}

function requireIdentifier(value: string, name: string): void {
  if (!value || value.length > 200 || /[\r\n\0]/u.test(value)) {
    throw new Error(`External shadow ${name} is invalid`);
  }
}

function validateRequestEnvelope(request: ExternalShadowRequest): void {
  if (request.protocol_version !== 1) throw new Error("External shadow protocol version is invalid");
  requireIdentifier(request.request_id, "request id");
  if (!UUID_PATTERN.test(request.chat_session_id) || !UUID_PATTERN.test(request.agent_session_id)) {
    throw new Error("External shadow session identity is invalid");
  }
  if (
    !SHA256_PATTERN.test(request.expected_prompt_sha256)
    || !SHA256_PATTERN.test(request.expected_tool_names_sha256)
    || !SHA256_PATTERN.test(request.expected_transcript_sha256)
  ) {
    throw new Error("External shadow expected profile is invalid");
  }
  if (
    !request.transcript_entries.length
    || request.transcript_entries.length > MAX_EXTERNAL_SHADOW_TRANSCRIPT_ENTRIES
  ) {
    throw new Error("External shadow transcript count is invalid");
  }
  const transcriptBytes = Buffer.byteLength(JSON.stringify(request.transcript_entries));
  if (transcriptBytes > MAX_TRANSCRIPT_BYTES) throw new Error("External shadow transcript is too large");

  const header = request.transcript_entries[0];
  if (header?.type !== "session" || header.id !== request.agent_session_id) {
    throw new Error("External shadow transcript header is invalid");
  }
  const entryIds = new Set<string>();
  for (const [ordinal, entry] of request.transcript_entries.entries()) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      throw new Error("External shadow transcript entry is invalid");
    }
    if (ordinal === 0) continue;
    const id = entry.id;
    if (typeof id !== "string" || !id || id.length > 255 || entryIds.has(id)) {
      throw new Error("External shadow transcript entry identity is invalid");
    }
    const parentId = entry.parentId;
    if (parentId !== null && (typeof parentId !== "string" || !entryIds.has(parentId))) {
      throw new Error("External shadow transcript parent is invalid");
    }
    entryIds.add(id);
  }
  if (request.current_leaf_id !== null && !entryIds.has(request.current_leaf_id)) {
    throw new Error("External shadow current leaf is absent from the transcript");
  }
}

function validateProfile(profile: ExternalWorkerProfile): void {
  if (
    Buffer.byteLength(profile.prompt) > MAX_PROMPT_BYTES
    || profile.tool_names.length > MAX_TOOL_NAMES
    || profile.tool_names.some((name) => !name || name.length > 128 || /[\r\n\0]/u.test(name))
    || new Set(profile.tool_names).size !== profile.tool_names.length
  ) {
    throw new Error("External shadow worker profile is invalid");
  }
}

export async function restoreShadowTranscript(
  request: ExternalShadowRequest,
): Promise<RestoredShadowTranscript> {
  validateRequestEnvelope(request);
  const root = await mkdtemp(path.join(os.tmpdir(), "pwc-external-pi-shadow-"));
  try {
    const sessionDirectory = path.join(root, "sessions");
    const workspaceDirectory = path.join(root, "workspace");
    await Promise.all([
      mkdir(sessionDirectory, { mode: 0o700 }),
      mkdir(workspaceDirectory, { mode: 0o700 }),
    ]);
    const sessionFile = path.join(sessionDirectory, `${request.agent_session_id}.jsonl`);
    await writeFile(
      sessionFile,
      `${request.transcript_entries.map((entry) => JSON.stringify(entry)).join("\n")}\n`,
      { mode: 0o600 },
    );
    const manager = SessionManager.open(sessionFile, sessionDirectory, workspaceDirectory);
    const restored = {
      agent_session_id: manager.getSessionId(),
      current_leaf_id: manager.getLeafId(),
      entry_count: manager.getEntries().length + 1,
    };
    if (
      restored.agent_session_id !== request.agent_session_id
      || restored.current_leaf_id !== request.current_leaf_id
      || restored.entry_count !== request.transcript_entries.length
    ) {
      throw new Error("External shadow native transcript restore mismatched");
    }
    return restored;
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

export function projectShadowState(
  request: ExternalShadowRequest,
  profile: ExternalWorkerProfile,
): ExternalShadowProjection {
  validateRequestEnvelope(request);
  validateProfile(profile);
  return {
    protocol_version: 1,
    request_id: request.request_id,
    chat_session_id: request.chat_session_id,
    agent_session_id: request.agent_session_id,
    current_leaf_id: request.current_leaf_id,
    entry_count: request.transcript_entries.length,
    transcript_sha256: nativeJsonlTranscriptDigest(request.transcript_entries),
    prompt_sha256: sha256(profile.prompt),
    tool_names_sha256: toolNameDigest(profile.tool_names),
  };
}

const COMPATIBILITY_FIELDS: (keyof ExternalShadowProjection)[] = [
  "protocol_version",
  "chat_session_id",
  "agent_session_id",
  "current_leaf_id",
  "entry_count",
  "transcript_sha256",
  "prompt_sha256",
  "tool_names_sha256",
];

export function compareShadowState(
  expected: ExternalShadowProjection,
  actual: ExternalShadowProjection,
): ExternalShadowComparison {
  if (!SHA256_PATTERN.test(expected.prompt_sha256) || !SHA256_PATTERN.test(actual.prompt_sha256)) {
    throw new Error("External shadow prompt digest is invalid");
  }
  const mismatches = COMPATIBILITY_FIELDS.filter((field) => expected[field] !== actual[field]);
  return { compatible: mismatches.length === 0, mismatches };
}

import { type RunTurn } from "./agent.js";

export const MAX_TURN_FRAME_BYTES = 2 * 1024 * 1024 + 256 * 1024;

export interface ExternalRunTurn extends RunTurn {
  turn_id: string;
  excalidraw_enabled: boolean;
  turnClaim: TurnClaimFrame;
  capability: string;
  gateway_url: string;
}

export interface TurnClaimFrame {
  turnId: string;
  workerId: string;
  workerGeneration: number | string;
  leaseGeneration: number | string;
}

export interface AttachTurn {
  v: 1;
  type: "attach_turn";
  request_id: string;
  turnClaim: TurnClaimFrame;
  afterSequence: number;
}

export interface CancelTurn {
  v: 1;
  type: "cancel_turn";
  request_id: string;
  turnClaim: TurnClaimFrame;
}

export interface AcknowledgeTerminal {
  v: 1;
  type: "ack_terminal";
  request_id: string;
  turnClaim: TurnClaimFrame;
  sequence: number;
}

export class TurnProtocolError extends Error {}

function validGeneration(value: unknown): value is number | string {
  if (Number.isSafeInteger(value) && (value as number) >= 1) return true;
  if (typeof value !== "string" || !/^[1-9][0-9]{0,18}$/u.test(value)) return false;
  return BigInt(value) <= 9_223_372_036_854_775_807n;
}

function parseTurnClaim(value: unknown): TurnClaimFrame {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TurnProtocolError("Invalid Pi turn claim");
  }
  const claim = value as Record<string, unknown>;
  if (
    Object.keys(claim).length !== 4
    || typeof claim.turnId !== "string"
    || !claim.turnId
    || typeof claim.workerId !== "string"
    || !claim.workerId
    || !validGeneration(claim.workerGeneration)
    || !validGeneration(claim.leaseGeneration)
  ) {
    throw new TurnProtocolError("Invalid Pi turn claim");
  }
  return claim as unknown as TurnClaimFrame;
}

export function claimsEqual(left: TurnClaimFrame, right: TurnClaimFrame): boolean {
  return left.turnId === right.turnId
    && left.workerId === right.workerId
    && left.workerGeneration === right.workerGeneration
    && left.leaseGeneration === right.leaseGeneration;
}

export function parseAttachTurn(
  value: unknown,
  expectedClaim?: TurnClaimFrame,
): AttachTurn {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TurnProtocolError("Invalid Pi attach frame");
  }
  const frame = value as Record<string, unknown>;
  if (
    Object.keys(frame).length !== 5
    || frame.v !== 1
    || frame.type !== "attach_turn"
    || typeof frame.request_id !== "string"
    || !frame.request_id
    || !Number.isSafeInteger(frame.afterSequence)
    || (frame.afterSequence as number) < 0
  ) {
    throw new TurnProtocolError("Invalid Pi attach frame");
  }
  const turnClaim = parseTurnClaim(frame.turnClaim);
  if (expectedClaim && !claimsEqual(turnClaim, expectedClaim)) {
    throw new TurnProtocolError("Stale Pi turn claim");
  }
  return { ...frame, turnClaim } as unknown as AttachTurn;
}

export function parseCancelTurn(
  value: unknown,
  expectedClaim?: TurnClaimFrame,
): CancelTurn {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TurnProtocolError("Invalid Pi cancel frame");
  }
  const frame = value as Record<string, unknown>;
  if (
    Object.keys(frame).length !== 4
    || frame.v !== 1
    || frame.type !== "cancel_turn"
    || typeof frame.request_id !== "string"
    || !frame.request_id
  ) throw new TurnProtocolError("Invalid Pi cancel frame");
  const turnClaim = parseTurnClaim(frame.turnClaim);
  if (expectedClaim && !claimsEqual(turnClaim, expectedClaim)) {
    throw new TurnProtocolError("Stale Pi turn claim");
  }
  return { ...frame, turnClaim } as unknown as CancelTurn;
}

export function parseAcknowledgeTerminal(
  value: unknown,
  expectedClaim?: TurnClaimFrame,
): AcknowledgeTerminal {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TurnProtocolError("Invalid Pi terminal acknowledgement");
  }
  const frame = value as Record<string, unknown>;
  if (
    Object.keys(frame).length !== 5
    || frame.v !== 1
    || frame.type !== "ack_terminal"
    || typeof frame.request_id !== "string"
    || !frame.request_id
    || !Number.isSafeInteger(frame.sequence)
    || (frame.sequence as number) < 1
  ) throw new TurnProtocolError("Invalid Pi terminal acknowledgement");
  const turnClaim = parseTurnClaim(frame.turnClaim);
  if (expectedClaim && !claimsEqual(turnClaim, expectedClaim)) {
    throw new TurnProtocolError("Stale Pi turn claim");
  }
  return { ...frame, turnClaim } as unknown as AcknowledgeTerminal;
}

export function parseAcknowledgeEvents(
  value: unknown,
  expectedClaim?: TurnClaimFrame,
): Omit<AcknowledgeTerminal, "type"> & { type: "ack_events" } {
  if (!value || typeof value !== "object" || Array.isArray(value)
    || (value as Record<string, unknown>).type !== "ack_events") {
    throw new TurnProtocolError("Invalid Pi event acknowledgement");
  }
  const parsed = parseAcknowledgeTerminal({ ...value, type: "ack_terminal" }, expectedClaim);
  return { ...parsed, type: "ack_events" };
}

export function parseRunTurn(value: unknown, external: true): ExternalRunTurn;
export function parseRunTurn(value: unknown, external?: false): RunTurn;
export function parseRunTurn(value: unknown, external = false): RunTurn | ExternalRunTurn {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TurnProtocolError("Invalid Pi run frame");
  }
  const frame = value as Record<string, unknown>;
  const required = new Set([
    "v", "type", "request_id", "chat_session_id", "prompt", "model", "resume",
    "web_search_enabled", "reasoning_effort", "fetchable_urls", "hf_username", "agent_harness",
  ]);
  if (external) {
    required.add("turn_id");
    required.add("turnClaim");
    required.add("capability");
    required.add("gateway_url");
    required.add("excalidraw_enabled");
  }
  const optional = new Set([
    "turn_id", "assignment_token", "worker_generation", "reader_mode", "poster_mode",
    "paper_artifacts_enabled", "paper_descriptor", "provider_protocol", "agent_session_id",
  ]);
  if (Object.keys(frame).some((key) => !required.has(key) && !optional.has(key))) {
    throw new TurnProtocolError("Invalid Pi run frame keys");
  }
  if ([...required].some((key) => !(key in frame))) throw new TurnProtocolError("Missing Pi run frame key");
  const turnClaim = external ? parseTurnClaim(frame.turnClaim) : undefined;
  if (
    frame.v !== 1 || frame.type !== "run_turn" || frame.agent_harness !== "pi" ||
    typeof frame.request_id !== "string" || typeof frame.chat_session_id !== "string" ||
    typeof frame.prompt !== "string" || Buffer.byteLength(frame.prompt) > 2 * 1024 * 1024 ||
    typeof frame.model !== "string" ||
    (frame.provider_protocol !== undefined
      && !new Set(["anthropic-messages", "openai-responses"]).has(String(frame.provider_protocol))) ||
    (frame.resume !== null && typeof frame.resume !== "string") ||
    (frame.agent_session_id !== undefined && (
      typeof frame.agent_session_id !== "string"
      || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu.test(frame.agent_session_id)
      || frame.resume !== null
    )) ||
    typeof frame.web_search_enabled !== "boolean" ||
    (frame.excalidraw_enabled !== undefined && typeof frame.excalidraw_enabled !== "boolean") ||
    (frame.reader_mode !== undefined && typeof frame.reader_mode !== "boolean") ||
    (frame.poster_mode !== undefined && typeof frame.poster_mode !== "boolean") ||
    (frame.paper_artifacts_enabled !== undefined && typeof frame.paper_artifacts_enabled !== "boolean") ||
    (frame.paper_descriptor !== undefined && (!frame.paper_descriptor || typeof frame.paper_descriptor !== "object" || Array.isArray(frame.paper_descriptor))) ||
    !new Set(["low", "medium", "high", "max"]).has(String(frame.reasoning_effort)) ||
    typeof frame.hf_username !== "string" || !Array.isArray(frame.fetchable_urls) ||
    (external && (
      typeof frame.turn_id !== "string" || !frame.turn_id ||
      turnClaim?.turnId !== frame.turn_id ||
      typeof frame.capability !== "string" || !frame.capability ||
      typeof frame.gateway_url !== "string" || !frame.gateway_url.startsWith("https://")
    ))
  ) throw new TurnProtocolError("Invalid Pi run frame value");
  return {
    ...frame,
    reader_mode: frame.reader_mode === true,
    poster_mode: frame.poster_mode === true,
    paper_artifacts_enabled: frame.paper_artifacts_enabled === true,
  } as unknown as RunTurn | ExternalRunTurn;
}

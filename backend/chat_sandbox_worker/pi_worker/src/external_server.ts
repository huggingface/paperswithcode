import { createHash, timingSafeEqual } from "node:crypto";
import http, { type IncomingMessage, type ServerResponse } from "node:http";
import { WebSocket, WebSocketServer } from "ws";

import { type RunTurn } from "./agent.js";
import { type PwCEvent } from "./events.js";
import { type RemoteToolChannel, type RemoteToolResult } from "./external_tools.js";
import { handleExternalFrame, MAX_EXTERNAL_FRAME_BYTES } from "./external_worker.js";
import { type ExternalWorkerProfile } from "./external_shadow.js";
import { ExternalTurnRegistry } from "./external_turn_registry.js";
import {
  type ExternalRunTurn,
  parseAcknowledgeTerminal,
  parseAcknowledgeEvents,
  parseAttachTurn,
  parseCancelTurn,
  parseRunTurn,
  TurnProtocolError,
} from "./turn_protocol.js";

interface ExternalTurnWorker {
  run(run: RunTurn): Promise<void>;
  cancel(requestId: string): Promise<void>;
  dispose(): Promise<void>;
}

type TurnEmitter = (requestId: string, event: PwCEvent) => void;

interface ExternalWorkerServerOptions {
  token: string;
  maximumConcurrent: number;
  workerId: string;
  instanceId: string;
  releaseId: string;
  profile: ExternalWorkerProfile;
  operationCounters?: ExternalOperationCounters;
  capabilityEvidence?: {
    provider_credentials_present: boolean;
    modal_credentials_present: boolean;
  };
  createTurnWorker?: (
    emit: TurnEmitter,
    run: ExternalRunTurn,
    channel: RemoteToolChannel,
  ) => ExternalTurnWorker;
}

export interface ExternalOperationCounters {
  shadow_requests: number;
  model_calls: number;
  tool_calls: number;
  provider_calls: number;
  modal_calls: number;
  billing_events: number;
}

function tokenDigest(value: string): Buffer {
  return createHash("sha256").update(value, "utf8").digest();
}

function authorized(request: IncomingMessage, expected: Buffer): boolean {
  const authorization = request.headers.authorization ?? "";
  const [scheme, token, extra] = authorization.split(" ");
  return scheme === "Bearer"
    && typeof token === "string"
    && extra === undefined
    && timingSafeEqual(tokenDigest(token), expected);
}

function json(response: ServerResponse, status: number, payload: object): void {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
  });
  response.end(body);
}

async function readBody(request: IncomingMessage): Promise<Buffer> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const bytes = Buffer.from(chunk);
    size += bytes.length;
    if (size > MAX_EXTERNAL_FRAME_BYTES) throw new Error("request_too_large");
    chunks.push(bytes);
  }
  return Buffer.concat(chunks, size);
}

export function createExternalWorkerServer(options: ExternalWorkerServerOptions): http.Server {
  if (options.token.length < 32) throw new Error("External worker token is too short");
  if (!Number.isInteger(options.maximumConcurrent) || options.maximumConcurrent < 1 || options.maximumConcurrent > 32) {
    throw new Error("External worker concurrency is invalid");
  }
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(options.workerId)) {
    throw new Error("External worker identity is invalid");
  }
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(options.instanceId)) {
    throw new Error("External worker instance is invalid");
  }
  if (!options.releaseId || options.releaseId.length > 255) {
    throw new Error("External worker release is invalid");
  }
  const expectedToken = tokenDigest(options.token);
  const requireAuthorization = (
    request: IncomingMessage,
    response: ServerResponse,
  ): boolean => {
    if (authorized(request, expectedToken)) return true;
    json(response, 401, { code: "unauthorized" });
    return false;
  };
  let shadowActive = 0;
  let state: "ready" | "draining" = "ready";
  let workerGeneration: number | null = null;
  const operationCounters = options.operationCounters ?? {
    shadow_requests: 0, model_calls: 0, tool_calls: 0, provider_calls: 0,
    modal_calls: 0, billing_events: 0,
  };
  const capabilityEvidence = options.capabilityEvidence ?? {
    provider_credentials_present: false,
    modal_credentials_present: false,
  };
  const activeSessions = () => shadowActive + turns.size;
  const status = () => ({
    protocol: "external-pi-v1",
    worker_id: options.workerId,
    instance_id: options.instanceId,
    release_id: options.releaseId,
    state,
    active_sessions: activeSessions(),
    maximum_sessions: options.maximumConcurrent,
    worker_generation: workerGeneration,
    operation_counters: { ...operationCounters },
    capability_evidence: {
      ...capabilityEvidence,
      registered_tool_count: options.profile.tool_names.length,
    },
  });
  const server = http.createServer(async (request, response) => {
    if (request.method === "GET" && request.url === "/health") {
      json(response, 200, {
        status: "ok",
        mode: options.createTurnWorker ? "active" : "shadow",
        protocol: "external-pi-v1",
        active: activeSessions(),
        capacity: options.maximumConcurrent,
      });
      return;
    }
    if (request.method === "GET" && request.url === "/v1/status") {
      if (!requireAuthorization(request, response)) return;
      json(response, 200, status());
      return;
    }
    if (request.method === "POST" && request.url === "/v1/claim") {
      if (!requireAuthorization(request, response)) return;
      try {
        const value = JSON.parse((await readBody(request)).toString("utf8")) as unknown;
        if (
          !value
          || typeof value !== "object"
          || Array.isArray(value)
          || Object.keys(value).length !== 1
          || !("worker_generation" in value)
          || !Number.isSafeInteger(value.worker_generation)
          || (value.worker_generation as number) < 1
          || (workerGeneration !== null && (value.worker_generation as number) < workerGeneration)
        ) {
          throw new Error("invalid_worker_generation");
        }
        const claimed = value.worker_generation as number;
        // Draining is otherwise terminal for this process, so a supervisor that
        // restarts after a drain can never register and systemd retries it
        // forever. An idle drained worker is scrap that a strictly newer lease
        // owner may reclaim; the higher generation still fences the old owner.
        if (state === "draining") {
          if (
            activeSessions() > 0
            || workerGeneration === null
            || claimed <= workerGeneration
          ) {
            throw new Error("invalid_worker_generation");
          }
          state = "ready";
        }
        workerGeneration = claimed;
        json(response, 200, status());
      } catch {
        json(response, 400, { code: "invalid_worker_claim" });
      }
      return;
    }
    if (request.method === "POST" && request.url === "/v1/drain") {
      if (!requireAuthorization(request, response)) return;
      if (
        workerGeneration === null
        || request.headers["x-pwc-worker-generation"] !== String(workerGeneration)
      ) {
        json(response, 409, { code: "stale_worker_generation" });
        return;
      }
      state = "draining";
      json(response, 200, status());
      return;
    }
    if (request.method !== "POST" || request.url !== "/v1/shadow") {
      json(response, 404, { code: "not_found" });
      return;
    }
    if (!requireAuthorization(request, response)) return;
    operationCounters.shadow_requests += 1;
    if (state === "draining") {
      json(response, 503, { code: "worker_draining" });
      return;
    }
    if (activeSessions() >= options.maximumConcurrent) {
      json(response, 503, { code: "shadow_capacity" });
      return;
    }
    shadowActive += 1;
    try {
      const body = await readBody(request);
      json(
        response,
        200,
        await handleExternalFrame(
          JSON.parse(body.toString("utf8")) as unknown,
          options.profile,
        ),
      );
    } catch (error) {
      const status = error instanceof Error && error.message === "request_too_large" ? 413 : 400;
      json(response, status, { code: "invalid_shadow_request" });
    } finally {
      shadowActive -= 1;
    }
  });
  const turnServer = new WebSocketServer({ noServer: true, maxPayload: MAX_EXTERNAL_FRAME_BYTES });
  const turns = new ExternalTurnRegistry();
  server.on("upgrade", (request, socket, head) => {
    if (request.url !== "/v1/turn") {
      socket.write("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n");
      socket.destroy();
      return;
    }
    if (!options.createTurnWorker || !authorized(request, expectedToken)) {
      socket.write("HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n");
      socket.destroy();
      return;
    }
    if (
      workerGeneration === null
      || request.headers["x-pwc-worker-generation"] !== String(workerGeneration)
    ) {
      socket.write("HTTP/1.1 409 Conflict\r\nConnection: close\r\n\r\n");
      socket.destroy();
      return;
    }
    turnServer.handleUpgrade(request, socket, head, (websocket) => {
      turnServer.emit("connection", websocket, request);
    });
  });
  turnServer.on("connection", (socket) => {
    let started = false;
    let acceptingFrames = true;
    let retained: ReturnType<ExternalTurnRegistry["start"]> | undefined;
    const reject = (code: number, reason: string): void => {
      acceptingFrames = false;
      socket.close(code, reason);
    };
    socket.on("message", (data, isBinary) => {
      if (!acceptingFrames) return;
      if (isBinary) {
        reject(1003, "invalid_frame");
        return;
      }
      let frame: Record<string, unknown>;
      try {
        frame = JSON.parse(data.toString()) as Record<string, unknown>;
      } catch {
        reject(1007, "invalid_json");
        return;
      }
      if (frame.type === "tool_result" && typeof frame.operation_id === "string") {
        try {
          if (!retained) throw new TurnProtocolError("Unknown Pi turn");
          retained.resolveTool(frame as unknown as RemoteToolResult);
        } catch (error) {
          if (!(error instanceof TurnProtocolError)) throw error;
          reject(1008, "uncorrelated_tool_result");
        }
        return;
      }
      if (frame.type === "cancel_turn") {
        try {
          const cancel = parseCancelTurn(frame, retained?.claim);
          const target = retained ?? turns.require(
            cancel.request_id, cancel.turnClaim,
          );
          if (cancel.request_id !== target.requestId) throw new TurnProtocolError("Unknown Pi turn");
          void target.cancel().catch(() => undefined);
          started = true;
        } catch (error) {
          if (!(error instanceof TurnProtocolError)) throw error;
          reject(1008, "invalid_cancel");
        }
        return;
      }
      if (frame.type === "ack_events") {
        try {
          const acknowledgement = parseAcknowledgeEvents(frame, retained?.claim);
          const target = turns.require(acknowledgement.request_id, acknowledgement.turnClaim);
          if (retained !== target) throw new TurnProtocolError("Unknown Pi turn");
          target.acknowledgeEvents(acknowledgement.sequence);
        } catch (error) {
          if (!(error instanceof TurnProtocolError)) throw error;
          reject(1008, "invalid_event_ack");
        }
        return;
      }
      if (frame.type === "ack_terminal") {
        try {
          const acknowledgement = parseAcknowledgeTerminal(frame, retained?.claim);
          turns.acknowledgeTerminal(
            acknowledgement.request_id,
            acknowledgement.turnClaim,
            acknowledgement.sequence,
          );
        } catch (error) {
          if (!(error instanceof TurnProtocolError)) throw error;
          reject(1008, "invalid_terminal_ack");
        }
        return;
      }
      if (started) {
        reject(1008, "turn_already_started");
        return;
      }
      started = true;
      if (frame.type === "attach_turn") {
        try {
          const attach = parseAttachTurn(frame);
          const target = turns.require(attach.request_id, attach.turnClaim);
          target.attach(socket, attach.turnClaim, attach.afterSequence);
          retained = target;
        } catch (error) {
          if (!(error instanceof TurnProtocolError)) throw error;
          reject(1008, "invalid_attach");
        }
        return;
      }
      let run: ExternalRunTurn;
      try {
        run = parseRunTurn(frame, true) as ExternalRunTurn;
      } catch (error) {
        if (!(error instanceof TurnProtocolError)) throw error;
        reject(1008, "invalid_request");
        return;
      }
      if (state !== "ready" || activeSessions() >= options.maximumConcurrent) {
        reject(1013, "worker_capacity");
        return;
      }
      let candidate: ReturnType<ExternalTurnRegistry["start"]> | undefined;
      try {
        candidate = turns.start(run.request_id, run.turnClaim, socket);
        const worker = options.createTurnWorker!(candidate.emit, run, candidate.channel);
        candidate.setCancelWorker(() => worker.cancel(run.request_id));
        candidate.setDisposeWorker(() => worker.dispose());
        const running = worker.run(run);
        retained = candidate;
        operationCounters.model_calls += 1;
        void running;
      } catch {
        candidate?.rejectStart();
        reject(1008, "turn_start_rejected");
      }
    });
    socket.on("close", () => {
      retained?.detach(socket);
    });
  });
  server.on("close", () => turnServer.close());
  return server;
}

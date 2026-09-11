import { createHash } from "node:crypto";

import { type PwCEvent } from "./events.js";
import {
  claimsEqual,
  type TurnClaimFrame,
  TurnProtocolError,
} from "./turn_protocol.js";
import {
  type RemoteToolChannel,
  type RemoteToolRequest,
  type RemoteToolResult,
} from "./external_tools.js";

export interface ExternalTurnTransport {
  send(data: string, callback?: (error?: Error) => void): void;
}

export type SequencedTurnFrame = Record<string, unknown> & {
  type: string;
  worker_sequence: number;
};

interface ExternalTurnRegistryOptions {
  maximumEvents?: number;
  maximumBytes?: number;
  terminalGraceMs?: number;
}

const DEFAULT_MAXIMUM_EVENTS = 4096;
const DEFAULT_MAXIMUM_BYTES = 8 * 1024 * 1024;
const DEFAULT_TERMINAL_GRACE_MS = 30_000;
const TERMINAL_EVENT_RESERVE = 2;
const TERMINAL_BYTE_RESERVE = 1024;

export class ExternalTurnRun {
  readonly channel: RemoteToolChannel;
  private transport: ExternalTurnTransport | undefined;
  private sequence = 0;
  private bufferedBytes = 0;
  private readonly frames: SequencedTurnFrame[] = [];
  private readonly pendingTools = new Map<string, {
    resolve: (result: RemoteToolResult) => void;
    reject: (error: Error) => void;
  }>();
  private readonly completedToolDigests = new Map<string, string>();
  private cancelWorker: (() => Promise<void>) | undefined;
  private disposeWorker: (() => Promise<void>) | undefined;
  private cancellation: Promise<void> | undefined;
  private terminalSequence: number | undefined;
  private terminalTimer: NodeJS.Timeout | undefined;
  private released = false;

  constructor(
    readonly requestId: string,
    readonly claim: TurnClaimFrame,
    transport: ExternalTurnTransport,
    private readonly maximumEvents: number,
    private readonly maximumBytes: number,
    private readonly terminalGraceMs: number,
    private readonly release: () => void,
  ) {
    this.transport = transport;
    this.channel = { request: (frame) => this.requestTool(frame) };
  }

  setCancelWorker(cancel: () => Promise<void>): void {
    this.cancelWorker = cancel;
  }

  setDisposeWorker(dispose: () => Promise<void>): void {
    this.disposeWorker = dispose;
  }

  emit = (_requestId: string, event: PwCEvent): void => {
    this.append(event);
  };

  append(frame: PwCEvent | RemoteToolRequest): SequencedTurnFrame {
    if (this.terminalSequence !== undefined) {
      return this.frames[this.frames.length - 1]!;
    }
    const sequenced = this.sequenceFrame(frame);
    const bytes = Buffer.byteLength(JSON.stringify(sequenced));
    const terminal = frame.type === "worker_done";
    const eventLimit = terminal
      ? this.maximumEvents
      : this.maximumEvents - TERMINAL_EVENT_RESERVE;
    const byteLimit = terminal
      ? this.maximumBytes
      : this.maximumBytes - TERMINAL_BYTE_RESERVE;
    if (this.frames.length + 1 > eventLimit || this.bufferedBytes + bytes > byteLimit) {
      return this.failBuffer();
    }
    this.store(sequenced, bytes);
    if (terminal) this.markTerminal(sequenced.worker_sequence);
    return sequenced;
  }

  attach(
    transport: ExternalTurnTransport,
    claim: TurnClaimFrame,
    afterSequence: number,
  ): SequencedTurnFrame[] {
    if (!claimsEqual(this.claim, claim)) throw new TurnProtocolError("Stale Pi turn claim");
    if (this.transport) throw new TurnProtocolError("Pi turn already has a transport");
    if (afterSequence > this.sequence) {
      throw new TurnProtocolError("Pi turn cursor is ahead of the run");
    }
    const replay = this.frames.filter((frame) => frame.worker_sequence > afterSequence);
    this.transport = transport;
    for (const frame of replay) this.send(frame);
    return replay;
  }

  detach(transport: ExternalTurnTransport): void {
    if (this.transport === transport) this.transport = undefined;
  }

  resolveTool(result: RemoteToolResult): void {
    const pending = this.pendingTools.get(result.operation_id);
    const digest = createHash("sha256").update(JSON.stringify(result)).digest("hex");
    if (!pending) {
      if (this.completedToolDigests.get(result.operation_id) === digest) return;
      throw new TurnProtocolError("Uncorrelated Pi tool result");
    }
    this.pendingTools.delete(result.operation_id);
    this.completedToolDigests.set(result.operation_id, digest);
    pending.resolve(result);
  }

  async cancel(): Promise<void> {
    if (!this.cancellation) {
      this.cancellation = this.cancelWorker?.() ?? Promise.resolve();
    }
    await this.cancellation;
  }

  acknowledgeTerminal(sequence: number): void {
    if (this.terminalSequence === undefined || sequence !== this.terminalSequence) {
      throw new TurnProtocolError("Pi turn terminal is not acknowledged");
    }
    this.dispose();
  }

  rejectStart(): void {
    this.dispose();
  }

  private requestTool(frame: RemoteToolRequest): Promise<RemoteToolResult> {
    if (this.terminalSequence !== undefined) {
      return Promise.reject(new TurnProtocolError("Pi turn is terminal"));
    }
    if (
      this.pendingTools.has(frame.operation_id)
      || this.completedToolDigests.has(frame.operation_id)
    ) {
      return Promise.reject(new TurnProtocolError("Duplicate Pi tool operation"));
    }
    return new Promise((resolve, reject) => {
      this.pendingTools.set(frame.operation_id, { resolve, reject });
      this.append(frame);
    });
  }

  private send(frame: SequencedTurnFrame): void {
    const transport = this.transport;
    if (!transport) return;
    try {
      transport.send(JSON.stringify(frame), (error) => {
        if (error) this.detach(transport);
      });
    } catch {
      this.detach(transport);
    }
  }

  private sequenceFrame(frame: PwCEvent | RemoteToolRequest): SequencedTurnFrame {
    return { ...frame, worker_sequence: this.sequence + 1 };
  }

  private store(frame: SequencedTurnFrame, bytes = Buffer.byteLength(JSON.stringify(frame))): void {
    if (frame.worker_sequence !== this.sequence + 1) {
      throw new TurnProtocolError("Pi turn frame sequence is invalid");
    }
    this.sequence = frame.worker_sequence;
    this.frames.push(frame);
    this.bufferedBytes += bytes;
    this.send(frame);
  }

  private failBuffer(): SequencedTurnFrame {
    const failure = this.sequenceFrame({
      type: "error",
      code: "worker_event_buffer_exhausted",
      message: "The research run failed.",
    });
    this.store(failure);
    const done = this.sequenceFrame({ type: "worker_done", status: "complete" });
    this.store(done);
    this.markTerminal(done.worker_sequence);
    for (const pending of this.pendingTools.values()) {
      pending.reject(new TurnProtocolError("Pi turn event buffer is exhausted"));
    }
    this.pendingTools.clear();
    void this.cancel().catch(() => undefined);
    return done;
  }

  private markTerminal(sequence: number): void {
    this.terminalSequence = sequence;
    this.terminalTimer = setTimeout(() => this.dispose(), this.terminalGraceMs);
    this.terminalTimer.unref();
  }

  private dispose(): void {
    if (this.released) return;
    this.released = true;
    if (this.terminalTimer) clearTimeout(this.terminalTimer);
    for (const pending of this.pendingTools.values()) {
      pending.reject(new TurnProtocolError("Pi turn is terminal"));
    }
    this.pendingTools.clear();
    this.completedToolDigests.clear();
    this.frames.length = 0;
    this.bufferedBytes = 0;
    this.transport = undefined;
    void this.disposeWorker?.().catch(() => undefined);
    this.release();
  }
}

export class ExternalTurnRegistry {
  private readonly runs = new Map<string, ExternalTurnRun>();
  private readonly turnByRequest = new Map<string, string>();

  private readonly maximumEvents: number;
  private readonly maximumBytes: number;
  private readonly terminalGraceMs: number;

  constructor(options: ExternalTurnRegistryOptions = {}) {
    this.maximumEvents = options.maximumEvents ?? DEFAULT_MAXIMUM_EVENTS;
    this.maximumBytes = options.maximumBytes ?? DEFAULT_MAXIMUM_BYTES;
    this.terminalGraceMs = options.terminalGraceMs ?? DEFAULT_TERMINAL_GRACE_MS;
    if (this.maximumEvents < TERMINAL_EVENT_RESERVE + 1) {
      throw new Error("External turn event limit is too small");
    }
    if (this.maximumBytes <= TERMINAL_BYTE_RESERVE) {
      throw new Error("External turn byte limit is too small");
    }
    if (this.terminalGraceMs < 1) throw new Error("External turn grace is invalid");
  }

  get size(): number {
    return this.runs.size;
  }

  start(
    requestId: string,
    claim: TurnClaimFrame,
    transport: ExternalTurnTransport,
  ): ExternalTurnRun {
    if (this.runs.has(claim.turnId) || this.turnByRequest.has(requestId)) {
      throw new TurnProtocolError("Pi turn already exists");
    }
    const run = new ExternalTurnRun(
      requestId,
      claim,
      transport,
      this.maximumEvents,
      this.maximumBytes,
      this.terminalGraceMs,
      () => {
        if (this.runs.get(claim.turnId) === run) {
          this.runs.delete(claim.turnId);
          this.turnByRequest.delete(requestId);
        }
      },
    );
    this.runs.set(claim.turnId, run);
    this.turnByRequest.set(requestId, claim.turnId);
    return run;
  }

  require(requestId: string, claim: TurnClaimFrame): ExternalTurnRun {
    const run = this.runs.get(claim.turnId);
    if (!run || run.requestId !== requestId || !claimsEqual(run.claim, claim)) {
      throw new TurnProtocolError("Unknown or stale Pi turn");
    }
    return run;
  }

  acknowledgeTerminal(
    requestId: string,
    claim: TurnClaimFrame,
    sequence: number,
  ): void {
    this.require(requestId, claim).acknowledgeTerminal(sequence);
  }
}

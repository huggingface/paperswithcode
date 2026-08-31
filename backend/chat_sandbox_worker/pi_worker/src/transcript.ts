import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { gatewayHeaders, type GatewayContext } from "./provider.js";

const MAX_RESPONSE_BYTES = 30 * 1024 * 1024;
const MAX_QUEUE_ENTRIES = 256;
const MAX_QUEUE_BYTES = 2 * 1024 * 1024;
const BATCH_ENTRIES = 64;
const BATCH_BYTES = 512 * 1024;

interface Snapshot {
  agent_session_id: string;
  current_leaf_id: string | null;
  entry_count: number;
  byte_size: number;
  format_version: number;
  entries?: Record<string, unknown>[];
}

async function request(payload: Record<string, unknown>, gateway?: GatewayContext): Promise<unknown> {
  const response = await fetch(`${gateway?.url.replace(/\/$/u, "") ?? "http://127.0.0.1:8765"}/session-store`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(gateway ? gatewayHeaders(gateway) : {}),
    },
    body: JSON.stringify({ format: "pi", ...payload }),
  });
  const bytes = Buffer.from(await response.arrayBuffer());
  if (bytes.length > MAX_RESPONSE_BYTES) throw new Error("Pi transcript response is too large");
  if (!response.ok) throw new Error(`Pi transcript store rejected request (${response.status})`);
  return (JSON.parse(bytes.toString("utf8")) as { result: unknown }).result;
}

export async function createOrBind(agentSessionId: string, gateway?: GatewayContext): Promise<Snapshot> {
  return (await request({ action: "create_or_bind_session", agent_session_id: agentSessionId }, gateway)) as Snapshot;
}

export async function loadSession(agentSessionId: string, gateway?: GatewayContext): Promise<Snapshot> {
  return (await request({ action: "load_session", agent_session_id: agentSessionId }, gateway)) as Snapshot;
}

export async function restoreFile(agentSessionId: string, directory: string, gateway?: GatewayContext): Promise<{ file: string; snapshot: Snapshot }> {
  const snapshot = await loadSession(agentSessionId, gateway);
  if (snapshot.agent_session_id !== agentSessionId || snapshot.format_version !== 1 || !Array.isArray(snapshot.entries)) {
    throw new Error("Pi transcript restore contract mismatch");
  }
  const file = path.join(directory, `${agentSessionId}.jsonl`);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  await writeFile(file, `${snapshot.entries.map((entry) => JSON.stringify(entry)).join("\n")}\n`, { mode: 0o600 });
  return { file, snapshot };
}

interface QueuedEntry {
  ordinal: number;
  entry: Record<string, unknown>;
  bytes: number;
}

export class TranscriptMirror {
  private queue: QueuedEntry[] = [];
  private queueBytes = 0;
  private flushing: Promise<void> | undefined;
  private failed: Error | undefined;
  private durableLeaf: string | null;

  constructor(
    readonly agentSessionId: string,
    private nextOrdinal: number,
    initialLeaf: string | null,
    private readonly gateway?: GatewayContext,
  ) {
    this.durableLeaf = initialLeaf;
  }

  append(entry: Record<string, unknown>): void {
    if (this.failed) return;
    const bytes = Buffer.byteLength(JSON.stringify(entry));
    if (this.queue.length >= MAX_QUEUE_ENTRIES || this.queueBytes + bytes > MAX_QUEUE_BYTES) {
      this.failed = new Error("Pi transcript mirror queue exceeded its bound");
      return;
    }
    this.queue.push({ ordinal: this.nextOrdinal++, entry, bytes });
    this.queueBytes += bytes;
    if (this.queue.length >= BATCH_ENTRIES || this.queueBytes >= BATCH_BYTES) this.startFlush();
  }

  private startFlush(): void {
    if (this.flushing || !this.queue.length || this.failed) return;
    const batch: QueuedEntry[] = [];
    let bytes = 0;
    while (this.queue.length && batch.length < BATCH_ENTRIES) {
      const candidate = this.queue[0];
      if (!candidate || (batch.length && bytes + candidate.bytes > BATCH_BYTES)) break;
      batch.push(candidate);
      this.queue.shift();
      this.queueBytes -= candidate.bytes;
      bytes += candidate.bytes;
    }
    const batchLeaf = batch.reduce<string | null>((leaf, item) => {
      const type = item.entry.type;
      const id = item.entry.id;
      return type !== "session" && typeof id === "string" && id ? id : leaf;
    }, this.durableLeaf);
    this.flushing = request({
      action: "append_entries",
      agent_session_id: this.agentSessionId,
      current_leaf_id: batchLeaf,
      entries: batch.map(({ ordinal, entry }) => ({ ordinal, entry })),
    }, this.gateway)
      .then(() => {
        this.durableLeaf = batchLeaf;
      })
      .catch((error: unknown) => {
        this.failed = error instanceof Error ? error : new Error("Pi transcript mirror failed");
      })
      .finally(() => {
        this.flushing = undefined;
        if (this.queue.length && !this.failed) this.startFlush();
      });
  }

  async flush(): Promise<void> {
    while ((this.queue.length || this.flushing) && !this.failed) {
      this.startFlush();
      await this.flushing;
    }
    if (this.failed) throw this.failed;
  }
}

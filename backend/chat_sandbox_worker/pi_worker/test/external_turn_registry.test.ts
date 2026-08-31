import assert from "node:assert/strict";
import test from "node:test";

import {
  ExternalTurnRegistry,
  type ExternalTurnTransport,
} from "../src/external_turn_registry.js";
import { TurnProtocolError } from "../src/turn_protocol.js";

const claim = {
  turnId: "20000000-0000-4000-8000-000000000001",
  workerId: "api-1",
  workerGeneration: 4,
  leaseGeneration: 9,
};

class RecordingTransport implements ExternalTurnTransport {
  readonly frames: Record<string, unknown>[] = [];

  send(data: string): void {
    this.frames.push(JSON.parse(data) as Record<string, unknown>);
  }
}

test("registry replays only unacknowledged frames and fences attach identity", () => {
  const registry = new ExternalTurnRegistry();
  const first = new RecordingTransport();
  const run = registry.start("request-1", claim, first);
  run.append({ type: "answer_delta", text: "one" });
  run.append({ type: "answer_delta", text: "two" });
  run.detach(first);

  const second = new RecordingTransport();
  assert.deepEqual(
    run.attach(second, claim, 1).map((frame) => frame.worker_sequence),
    [2],
  );
  assert.deepEqual(second.frames.map((frame) => frame.worker_sequence), [2]);
  assert.throws(
    () => run.attach(new RecordingTransport(), claim, 2),
    TurnProtocolError,
  );
  run.detach(second);
  assert.throws(
    () => run.attach(new RecordingTransport(), claim, 3),
    TurnProtocolError,
  );
  assert.throws(
    () => run.attach(new RecordingTransport(), { ...claim, leaseGeneration: 10 }, 2),
    TurnProtocolError,
  );
  assert.throws(
    () => registry.start(
      "request-1",
      { ...claim, turnId: "20000000-0000-4000-8000-000000000002" },
      new RecordingTransport(),
    ),
    TurnProtocolError,
  );
});

test("explicit cancellation aborts the retained harness exactly once", async () => {
  const run = new ExternalTurnRegistry().start(
    "request-1", claim, new RecordingTransport(),
  );
  let aborts = 0;
  run.setCancelWorker(async () => { aborts += 1; });

  await run.cancel();
  await run.cancel();

  assert.equal(aborts, 1);
});

test("tool result ambiguity accepts only an exact correlated duplicate", async () => {
  const run = new ExternalTurnRegistry().start(
    "request-1", claim, new RecordingTransport(),
  );
  const pending = run.channel.request({
    type: "tool_request",
    operation_id: "operation-1",
    tool_call_id: "tool-1",
    operation: "read",
    path: "/workspace/result.txt",
    offset: 0,
    max_bytes: 1024,
  });
  const result = {
    type: "tool_result" as const,
    operation_id: "operation-1",
    ok: true,
    data_base64: "YW5zd2Vy",
    eof: true,
  };
  run.resolveTool(result);
  assert.equal((await pending).ok, true);
  assert.doesNotThrow(() => run.resolveTool(result));
  assert.throws(
    () => run.resolveTool({ ...result, data_base64: "Y29uZmxpY3Q=" }),
    TurnProtocolError,
  );
  assert.throws(
    () => run.resolveTool({ ...result, operation_id: "unknown" }),
    TurnProtocolError,
  );
  await assert.rejects(run.channel.request({
    type: "tool_request",
    operation_id: "operation-1",
    tool_call_id: "tool-2",
    operation: "read",
    path: "/workspace/other.txt",
    offset: 0,
    max_bytes: 1024,
  }), TurnProtocolError);
});

test("detached replay overflow fails closed with the canonical public code", async () => {
  const registry = new ExternalTurnRegistry({
    maximumEvents: 4,
    maximumBytes: 4096,
    terminalGraceMs: 1000,
  });
  const transport = new RecordingTransport();
  const run = registry.start("request-1", claim, transport);
  let aborts = 0;
  run.setCancelWorker(async () => { aborts += 1; });
  run.detach(transport);
  run.append({ type: "answer_delta", text: "one" });
  run.append({ type: "answer_delta", text: "two" });
  await assert.rejects(run.channel.request({
    type: "tool_request",
    operation_id: "operation-overflow",
    tool_call_id: "tool-overflow",
    operation: "read",
    path: "/workspace/result.txt",
    offset: 0,
    max_bytes: 1024,
  }), TurnProtocolError);
  await Promise.resolve();

  const replayTransport = new RecordingTransport();
  run.attach(replayTransport, claim, 0);
  assert.deepEqual(replayTransport.frames.map((frame) => frame.type), [
    "answer_delta", "answer_delta", "error", "worker_done",
  ]);
  assert.deepEqual(
    replayTransport.frames.map((frame) => frame.worker_sequence),
    [1, 2, 3, 4],
  );
  assert.equal(replayTransport.frames[2]?.code, "worker_event_buffer_exhausted");
  assert.equal(aborts, 1);
});

test("detached replay byte overflow fails before buffered content exceeds its bound", () => {
  const registry = new ExternalTurnRegistry({
    maximumEvents: 16,
    maximumBytes: 1200,
    terminalGraceMs: 1000,
  });
  const transport = new RecordingTransport();
  const run = registry.start("request-1", claim, transport);
  run.detach(transport);
  run.append({ type: "answer_delta", text: "x".repeat(400) });

  const replay = new RecordingTransport();
  run.attach(replay, claim, 0);
  assert.deepEqual(replay.frames.map((frame) => frame.type), [
    "error", "worker_done",
  ]);
  assert.equal(replay.frames[0]?.code, "worker_event_buffer_exhausted");
});

test("buffer overflow contains a rejected harness cancellation and still cleans terminal state", async () => {
  const registry = new ExternalTurnRegistry({
    maximumEvents: 3,
    maximumBytes: 4096,
    terminalGraceMs: 1000,
  });
  const transport = new RecordingTransport();
  const run = registry.start("request-1", claim, transport);
  let cancels = 0;
  run.setCancelWorker(async () => {
    cancels += 1;
    throw new Error("cancel failed");
  });
  run.detach(transport);
  run.append({ type: "answer_delta", text: "one" });
  run.append({ type: "answer_delta", text: "overflow" });
  await new Promise((resolve) => setImmediate(resolve));

  const replay = new RecordingTransport();
  run.attach(replay, claim, 0);
  assert.deepEqual(replay.frames.map((frame) => frame.type), [
    "answer_delta", "error", "worker_done",
  ]);
  assert.equal(cancels, 1);
  await assert.rejects(run.cancel(), /cancel failed/);
  assert.equal(cancels, 1);
  registry.acknowledgeTerminal("request-1", claim, 3);
  assert.equal(registry.size, 0);
});

test("terminal acknowledgement and grace expiry release retained state", async () => {
  const acknowledged = new ExternalTurnRegistry({ terminalGraceMs: 1000 });
  const first = acknowledged.start("request-1", claim, new RecordingTransport());
  first.append({ type: "worker_done", status: "complete" });
  assert.equal(acknowledged.size, 1);
  assert.throws(
    () => acknowledged.acknowledgeTerminal("request-1", claim, 2),
    TurnProtocolError,
  );
  acknowledged.acknowledgeTerminal("request-1", claim, 1);
  assert.equal(acknowledged.size, 0);

  const expired = new ExternalTurnRegistry({ terminalGraceMs: 5 });
  expired.start("request-1", claim, new RecordingTransport())
    .append({ type: "worker_done", status: "complete" });
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(expired.size, 0);
});

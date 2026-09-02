import assert from "node:assert/strict";
import { once } from "node:events";
import test from "node:test";
import WebSocket from "ws";

import { createExternalWorkerServer } from "../src/external_server.js";
import { toolNameDigest } from "../src/mcp_app_registry.js";
import { parseAttachTurn, TurnProtocolError } from "../src/turn_protocol.js";

const durableTurnClaim = {
  turnId: "20000000-0000-4000-8000-000000000001",
  workerId: "api-1",
  workerGeneration: 4,
  leaseGeneration: 9,
};

function externalRunFrame(): Record<string, unknown> {
  return {
    v: 1,
    type: "run_turn",
    request_id: "request-1",
    chat_session_id: "10000000-0000-4000-8000-000000000001",
    turn_id: durableTurnClaim.turnId,
    turnClaim: durableTurnClaim,
    prompt: "Answer without tools.",
    model: "test-model",
    resume: null,
    web_search_enabled: false,
    excalidraw_enabled: true,
    reader_mode: false,
    poster_mode: false,
    paper_artifacts_enabled: false,
    reasoning_effort: "low",
    fetchable_urls: [],
    hf_username: "qualification",
    agent_harness: "pi",
    provider_protocol: "openai-responses",
    capability: "opaque-turn-capability",
    gateway_url: "https://gateway.example.test/api/internal/chat-gateway",
  };
}

test("external shadow HTTP service authenticates and exposes no run endpoint", async () => {
  const server = createExternalWorkerServer({
    token: "s".repeat(32),
    maximumConcurrent: 8,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: ["bash", "read"] },
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const payload = {
    type: "shadow_compare",
    protocol_version: 1,
    request_id: "shadow-1",
    chat_session_id: "10000000-0000-4000-8000-000000000001",
    agent_session_id: "20000000-0000-4000-8000-000000000001",
    current_leaf_id: null,
    expected_prompt_sha256: "bbc5e661e106c6dcd8dc6dd186454c2fcba3c710fb4d8e71a60c93eaf077f073",
    expected_tool_names_sha256: toolNameDigest(["bash", "read"]),
    expected_transcript_sha256: "04ec741c240dd09ab5ca2495141ac79893266747fd5c0bf966aa463e6fe69b5a",
    transcript_entries: [{
      type: "session", id: "20000000-0000-4000-8000-000000000001", version: 3,
    }],
  };
  try {
    assert.equal((await fetch(`${baseUrl}/health`)).status, 200);
    assert.equal((await fetch(`${baseUrl}/v1/shadow`, { method: "POST" })).status, 401);
    assert.equal((await fetch(`${baseUrl}/v1/run`, {
      method: "POST",
      headers: { Authorization: `Bearer ${"s".repeat(32)}` },
    })).status, 404);
    const response = await fetch(`${baseUrl}/v1/shadow`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${"s".repeat(32)}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    assert.equal(response.status, 200);
    const projection = await response.json() as {
      type: string; prompt_sha256: string; tool_names_sha256: string;
    };
    assert.equal(projection.type, "shadow_projection");
    assert.equal(projection.prompt_sha256, payload.expected_prompt_sha256);
    assert.equal(projection.tool_names_sha256, payload.expected_tool_names_sha256);
  } finally {
    server.close();
    await once(server, "close");
  }
});

test("external worker streams one authenticated Pi turn without a local shell", async () => {
  const token = "s".repeat(32);
  const observed: Record<string, unknown>[] = [];
  let disposals = 0;
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 8,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: ["bash", "read"] },
    createTurnWorker: (emit, _run, channel) => ({
      async run(run) {
        observed.push(run as unknown as Record<string, unknown>);
        const tool = await channel.request({
          type: "tool_request", operation_id: "operation-1", tool_call_id: "tool-1",
          operation: "read", path: "/opt/pwc/PWC_CLI_SKILL.md", offset: 0,
          max_bytes: 1024,
        });
        assert.equal(tool.ok, true);
        emit(run.request_id, { type: "workspace_ready" });
        emit(run.request_id, { type: "done", finish_reason: "success", followups: [] });
        emit(run.request_id, { type: "worker_done", status: "complete" });
      },
      async cancel() {},
      async dispose() { disposals += 1; },
    }),
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const claim = await fetch(`${baseUrl}/v1/claim`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ worker_generation: 3 }),
  });
  assert.equal(claim.status, 200);
  const socket = new WebSocket(`ws://127.0.0.1:${address.port}/v1/turn`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "X-PWC-Worker-Generation": "3",
    },
  });
  const messages: Record<string, unknown>[] = [];
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(String(event.data)) as Record<string, unknown>;
    if (message.type === "tool_request") {
      socket.send(JSON.stringify({
        type: "tool_result", operation_id: message.operation_id, ok: true,
        data_base64: Buffer.from("guide").toString("base64"), eof: true,
      }));
      return;
    }
    messages.push(message);
  });
  try {
    await once(socket, "open");
    socket.send(JSON.stringify({
      v: 1,
      type: "run_turn",
      request_id: "request-1",
      chat_session_id: "10000000-0000-4000-8000-000000000001",
      turn_id: "20000000-0000-4000-8000-000000000001",
      turnClaim: {
        turnId: "20000000-0000-4000-8000-000000000001",
        workerId: "api-1",
        workerGeneration: 4,
        leaseGeneration: 9,
      },
      prompt: "Answer without tools.",
      model: "test-model",
      resume: null,
      web_search_enabled: false,
      excalidraw_enabled: true,
      reader_mode: false,
      poster_mode: false,
      paper_artifacts_enabled: false,
      reasoning_effort: "low",
      fetchable_urls: [],
      hf_username: "qualification",
      agent_harness: "pi",
      provider_protocol: "openai-responses",
      capability: "opaque-turn-capability",
      gateway_url: "https://gateway.example.test/api/internal/chat-gateway",
    }));
    while (!messages.some((message) => message.type === "worker_done")) {
      await once(socket, "message");
    }
    assert.deepEqual(messages.map((message) => message.type), [
      "workspace_ready", "done", "worker_done",
    ]);
    assert.equal(observed.length, 1);
    assert.equal(observed[0]?.capability, "opaque-turn-capability");
    assert.deepEqual(observed[0]?.turnClaim, {
      turnId: "20000000-0000-4000-8000-000000000001",
      workerId: "api-1",
      workerGeneration: 4,
      leaseGeneration: 9,
    });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(disposals, 0);
    const terminal = messages.find((message) => message.type === "worker_done");
    assert(terminal);
    socket.send(JSON.stringify({
      v: 1,
      type: "ack_terminal",
      request_id: "request-1",
      turnClaim: durableTurnClaim,
      sequence: terminal.worker_sequence,
    }));
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(disposals, 1);
  } finally {
    socket.close();
    server.close();
    await once(server, "close");
  }
});

test("external worker reattaches a pending tool request without restarting or cancelling Pi", async () => {
  const token = "s".repeat(32);
  let starts = 0;
  let cancels = 0;
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 8,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: ["read"] },
    createTurnWorker: (emit, _run, channel) => ({
      async run(run) {
        starts += 1;
        const result = await channel.request({
          type: "tool_request",
          operation_id: "operation-1",
          tool_call_id: "tool-1",
          operation: "read",
          path: "/workspace/result.txt",
          offset: 0,
          max_bytes: 1024,
        });
        assert.equal(result.ok, true);
        emit(run.request_id, { type: "done", finish_reason: "success", followups: [] });
        emit(run.request_id, { type: "worker_done", status: "complete" });
      },
      async cancel() { cancels += 1; },
      async dispose() {},
    }),
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  await fetch(`${baseUrl}/v1/claim`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ worker_generation: 3 }),
  });
  const connect = () => new WebSocket(`ws://127.0.0.1:${address.port}/v1/turn`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "X-PWC-Worker-Generation": "3",
    },
  });

  const first = connect();
  let second: WebSocket | undefined;
  try {
    await once(first, "open");
    first.send(JSON.stringify(externalRunFrame()));
    const [firstPayload] = await once(first, "message");
    const firstTool = JSON.parse(String(firstPayload)) as Record<string, unknown>;
    assert.equal(firstTool.type, "tool_request");
    assert.equal(firstTool.worker_sequence, 1);
    first.close();
    await once(first, "close");

    second = connect();
    await once(second, "open");
    second.send(JSON.stringify({
      v: 1,
      type: "attach_turn",
      request_id: "request-1",
      turnClaim: durableTurnClaim,
      afterSequence: 0,
    }));
    const [replayPayload] = await once(second, "message");
    const replay = JSON.parse(String(replayPayload)) as Record<string, unknown>;
    assert.equal(replay.type, "tool_request");
    assert.equal(replay.worker_sequence, 1);
    const terminal: Record<string, unknown>[] = [];
    const terminalDone = new Promise<void>((resolve) => {
      second!.addEventListener("message", (event) => {
        const message = JSON.parse(String(event.data)) as Record<string, unknown>;
        if (message.worker_sequence === 1) return;
        terminal.push(message);
        if (message.type === "worker_done") resolve();
      });
    });
    second.send(JSON.stringify({
      type: "tool_result",
      operation_id: "operation-1",
      ok: true,
      data_base64: Buffer.from("answer").toString("base64"),
      eof: true,
    }));
    await terminalDone;
    assert.deepEqual(terminal.map((frame) => frame.type), ["done", "worker_done"]);
    assert.equal(starts, 1);
    assert.equal(cancels, 0);
    second.close();
  } finally {
    first.terminate();
    second?.terminate();
    server.close();
    await once(server, "close");
  }
});

test("retained runs hold capacity across detach and release it on terminal acknowledgement", async () => {
  const token = "s".repeat(32);
  let starts = 0;
  let finish!: () => void;
  const completion = new Promise<void>((resolve) => { finish = resolve; });
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 1,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: [] },
    createTurnWorker: (emit) => ({
      async run(run) {
        starts += 1;
        emit(run.request_id, { type: "workspace_ready" });
        await completion;
        emit(run.request_id, { type: "worker_done", status: "complete" });
      },
      async cancel() {},
      async dispose() {},
    }),
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const authorization = { Authorization: `Bearer ${token}` };
  await fetch(`${baseUrl}/v1/claim`, {
    method: "POST",
    headers: { ...authorization, "Content-Type": "application/json" },
    body: JSON.stringify({ worker_generation: 3 }),
  });
  const connect = () => new WebSocket(`ws://127.0.0.1:${address.port}/v1/turn`, {
    headers: { ...authorization, "X-PWC-Worker-Generation": "3" },
  });
  const activeSessions = async () => Number((await (
    await fetch(`${baseUrl}/v1/status`, { headers: authorization })
  ).json() as { active_sessions: number }).active_sessions);
  const first = connect();
  let attached: WebSocket | undefined;
  let intruder: WebSocket | undefined;
  try {
    await once(first, "open");
    first.send(JSON.stringify(externalRunFrame()));
    await once(first, "message");
    first.close();
    await once(first, "close");
    assert.equal(await activeSessions(), 1);

    intruder = connect();
    await once(intruder, "open");
    const intruderClosed = once(intruder, "close");
    const intruderClaim = {
      ...durableTurnClaim,
      turnId: "20000000-0000-4000-8000-000000000002",
    };
    intruder.send(JSON.stringify({
      ...externalRunFrame(),
      request_id: "request-2",
      turn_id: intruderClaim.turnId,
      turnClaim: intruderClaim,
    }));
    const [intruderCode] = await intruderClosed;
    assert.equal(intruderCode, 1013);
    assert.equal(starts, 1);

    attached = connect();
    await once(attached, "open");
    attached.send(JSON.stringify({
      v: 1,
      type: "attach_turn",
      request_id: "request-1",
      turnClaim: durableTurnClaim,
      afterSequence: 1,
    }));
    assert.equal(await activeSessions(), 1);
    const terminal = once(attached, "message");
    finish();
    const [payload] = await terminal;
    const done = JSON.parse(String(payload)) as Record<string, unknown>;
    assert.equal(done.type, "worker_done");
    assert.equal(done.worker_sequence, 2);
    attached.send(JSON.stringify({
      v: 1,
      type: "ack_terminal",
      request_id: "request-1",
      turnClaim: durableTurnClaim,
      sequence: 2,
    }));
    await new Promise((resolve) => setTimeout(resolve, 10));
    assert.equal(await activeSessions(), 0);
  } finally {
    first.terminate();
    intruder?.terminate();
    attached?.terminate();
    server.close();
    await once(server, "close");
  }
});

test("authenticated detached cancellation requires the exact claim and aborts once", async () => {
  const token = "s".repeat(32);
  let cancels = 0;
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 1,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: [] },
    createTurnWorker: (emit) => ({
      async run(run) { emit(run.request_id, { type: "workspace_ready" }); },
      async cancel() {
        cancels += 1;
        throw new Error("cancel failed");
      },
      async dispose() {},
    }),
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const headers = {
    Authorization: `Bearer ${token}`,
    "X-PWC-Worker-Generation": "3",
  };
  await fetch(`${baseUrl}/v1/claim`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ worker_generation: 3 }),
  });
  const connect = () => new WebSocket(`ws://127.0.0.1:${address.port}/v1/turn`, { headers });
  const runSocket = connect();
  let stale: WebSocket | undefined;
  let control: WebSocket | undefined;
  try {
    await once(runSocket, "open");
    runSocket.send(JSON.stringify(externalRunFrame()));
    await once(runSocket, "message");
    runSocket.close();
    await once(runSocket, "close");

    stale = connect();
    await once(stale, "open");
    const staleClosed = once(stale, "close");
    stale.send(JSON.stringify({
      v: 1,
      type: "cancel_turn",
      request_id: "request-1",
      turnClaim: { ...durableTurnClaim, leaseGeneration: 10 },
    }));
    const [staleCode] = await staleClosed;
    assert.equal(staleCode, 1008);
    assert.equal(cancels, 0);

    control = connect();
    await once(control, "open");
    const cancel = {
      v: 1,
      type: "cancel_turn",
      request_id: "request-1",
      turnClaim: durableTurnClaim,
    };
    control.send(JSON.stringify(cancel));
    control.send(JSON.stringify(cancel));
    await new Promise((resolve) => setTimeout(resolve, 10));
    assert.equal(cancels, 1);
    const afterRejectedCancel = await (await fetch(`${baseUrl}/v1/status`, {
      headers: { Authorization: `Bearer ${token}` },
    })).json() as any;
    assert.equal(afterRejectedCancel.active_sessions, 1);
  } finally {
    runSocket.terminate();
    stale?.terminate();
    control?.terminate();
    server.close();
    await once(server, "close");
  }
});

test("external worker rejects a tool result without an attached retained run", async () => {
  const token = "s".repeat(32);
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 1,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: [] },
    createTurnWorker: () => ({
      async run() {}, async cancel() {}, async dispose() {},
    }),
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  await fetch(`${baseUrl}/v1/claim`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ worker_generation: 3 }),
  });
  const socket = new WebSocket(`ws://127.0.0.1:${address.port}/v1/turn`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "X-PWC-Worker-Generation": "3",
    },
  });
  try {
    await once(socket, "open");
    const closed = once(socket, "close");
    socket.send(JSON.stringify({
      type: "tool_result", operation_id: "unknown", ok: true,
    }));
    const result = await Promise.race([
      closed.then(([code]) => Number(code)),
      new Promise<number>((resolve) => setTimeout(() => resolve(0), 25)),
    ]);
    assert.equal(result, 1008);
  } finally {
    socket.terminate();
    server.close();
    await once(server, "close");
  }
});

test("duplicate run start is rejected without counting or disturbing the incumbent", async () => {
  const token = "s".repeat(32);
  let starts = 0;
  let finish!: () => void;
  const completion = new Promise<void>((resolve) => { finish = resolve; });
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 2,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: [] },
    createTurnWorker: (emit) => ({
      async run(run) {
        starts += 1;
        emit(run.request_id, { type: "workspace_ready" });
        await completion;
        emit(run.request_id, { type: "worker_done", status: "complete" });
      },
      async cancel() {},
      async dispose() {},
    }),
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const authorization = { Authorization: `Bearer ${token}` };
  await fetch(`${baseUrl}/v1/claim`, {
    method: "POST",
    headers: { ...authorization, "Content-Type": "application/json" },
    body: JSON.stringify({ worker_generation: 3 }),
  });
  const connect = () => new WebSocket(`ws://127.0.0.1:${address.port}/v1/turn`, {
    headers: { ...authorization, "X-PWC-Worker-Generation": "3" },
  });
  const incumbent = connect();
  let duplicate: WebSocket | undefined;
  let attached: WebSocket | undefined;
  try {
    await once(incumbent, "open");
    incumbent.send(JSON.stringify(externalRunFrame()));
    await once(incumbent, "message");
    incumbent.close();
    await once(incumbent, "close");

    duplicate = connect();
    await once(duplicate, "open");
    const duplicateClosed = once(duplicate, "close");
    duplicate.send(JSON.stringify(externalRunFrame()));
    const [duplicateCode] = await duplicateClosed;
    assert.equal(duplicateCode, 1008);
    const status = await (await fetch(`${baseUrl}/v1/status`, {
      headers: authorization,
    })).json() as any;
    assert.equal(status.operation_counters.model_calls, 1);
    assert.equal(starts, 1);

    attached = connect();
    await once(attached, "open");
    attached.send(JSON.stringify({
      v: 1,
      type: "attach_turn",
      request_id: "request-1",
      turnClaim: durableTurnClaim,
      afterSequence: 1,
    }));
    const terminal = once(attached, "message");
    finish();
    const [payload] = await terminal;
    assert.equal((JSON.parse(String(payload)) as any).type, "worker_done");
  } finally {
    incumbent.terminate();
    duplicate?.terminate();
    attached?.terminate();
    server.close();
    await once(server, "close");
  }
});

test("worker construction failure releases the provisional run without counting a model", async () => {
  const token = "s".repeat(32);
  let attempts = 0;
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 1,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: [] },
    createTurnWorker: (emit) => {
      attempts += 1;
      if (attempts === 1) {
        emit("request-1", { type: "workspace_ready" });
        throw new Error("construction failed");
      }
      return {
        async run(run) {
          emit(run.request_id, { type: "worker_done", status: "complete" });
        },
        async cancel() {},
        async dispose() {},
      };
    },
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const authorization = { Authorization: `Bearer ${token}` };
  await fetch(`${baseUrl}/v1/claim`, {
    method: "POST",
    headers: { ...authorization, "Content-Type": "application/json" },
    body: JSON.stringify({ worker_generation: 3 }),
  });
  const connect = () => new WebSocket(`ws://127.0.0.1:${address.port}/v1/turn`, {
    headers: { ...authorization, "X-PWC-Worker-Generation": "3" },
  });
  const failed = connect();
  let successful: WebSocket | undefined;
  try {
    await once(failed, "open");
    const failedClosed = once(failed, "close");
    failed.send(JSON.stringify(externalRunFrame()));
    const [failedCode] = await failedClosed;
    assert.equal(failedCode, 1008);
    const afterFailure = await (await fetch(`${baseUrl}/v1/status`, {
      headers: authorization,
    })).json() as any;
    assert.equal(afterFailure.active_sessions, 0);
    assert.equal(afterFailure.operation_counters.model_calls, 0);

    const nextClaim = {
      ...durableTurnClaim,
      turnId: "20000000-0000-4000-8000-000000000002",
    };
    successful = connect();
    await once(successful, "open");
    const terminal = once(successful, "message");
    successful.send(JSON.stringify({
      ...externalRunFrame(),
      request_id: "request-2",
      turn_id: nextClaim.turnId,
      turnClaim: nextClaim,
    }));
    const [payload] = await terminal;
    assert.equal((JSON.parse(String(payload)) as any).type, "worker_done");
    const afterSuccess = await (await fetch(`${baseUrl}/v1/status`, {
      headers: authorization,
    })).json() as any;
    assert.equal(afterSuccess.operation_counters.model_calls, 1);
  } finally {
    failed.terminate();
    successful?.terminate();
    server.close();
    await once(server, "close");
  }
});

test("rejected second attach has no authority over the incumbent run", async () => {
  const token = "s".repeat(32);
  let cancels = 0;
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 2,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: ["read"] },
    createTurnWorker: (emit, _run, channel) => ({
      async run(run) {
        const result = await channel.request({
          type: "tool_request",
          operation_id: "operation-1",
          tool_call_id: "tool-1",
          operation: "read",
          path: "/workspace/result.txt",
          offset: 0,
          max_bytes: 1024,
        });
        assert.equal(result.ok, true);
        emit(run.request_id, { type: "worker_done", status: "complete" });
      },
      async cancel() { cancels += 1; },
      async dispose() {},
    }),
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const authorization = { Authorization: `Bearer ${token}` };
  await fetch(`${baseUrl}/v1/claim`, {
    method: "POST",
    headers: { ...authorization, "Content-Type": "application/json" },
    body: JSON.stringify({ worker_generation: 3 }),
  });
  const connect = () => new WebSocket(`ws://127.0.0.1:${address.port}/v1/turn`, {
    headers: { ...authorization, "X-PWC-Worker-Generation": "3" },
  });
  const incumbent = connect();
  let rejected: WebSocket | undefined;
  let terminalRejected: WebSocket | undefined;
  try {
    await once(incumbent, "open");
    incumbent.send(JSON.stringify(externalRunFrame()));
    const [toolPayload] = await once(incumbent, "message");
    const tool = JSON.parse(String(toolPayload)) as any;
    assert.equal(tool.type, "tool_request");

    rejected = connect();
    await once(rejected, "open");
    const rejectedClosed = once(rejected, "close");
    rejected.send(JSON.stringify({
      v: 1,
      type: "attach_turn",
      request_id: "request-1",
      turnClaim: durableTurnClaim,
      afterSequence: 0,
    }));
    rejected.send(JSON.stringify({
      type: "tool_result", operation_id: "operation-1", ok: false,
    }));
    rejected.send(JSON.stringify({
      v: 1,
      type: "cancel_turn",
      request_id: "request-1",
      turnClaim: durableTurnClaim,
    }));
    const [rejectedCode] = await rejectedClosed;
    assert.equal(rejectedCode, 1008);
    assert.equal(cancels, 0);

    const terminal = once(incumbent, "message");
    incumbent.send(JSON.stringify({
      type: "tool_result",
      operation_id: "operation-1",
      ok: true,
      data_base64: "YW5zd2Vy",
      eof: true,
    }));
    const [terminalPayload] = await terminal;
    const terminalFrame = JSON.parse(String(terminalPayload)) as any;
    assert.equal(terminalFrame.type, "worker_done");

    terminalRejected = connect();
    await once(terminalRejected, "open");
    const terminalRejectedClosed = once(terminalRejected, "close");
    terminalRejected.send(JSON.stringify({
      v: 1,
      type: "attach_turn",
      request_id: "request-1",
      turnClaim: durableTurnClaim,
      afterSequence: 0,
    }));
    terminalRejected.send(JSON.stringify({
      v: 1,
      type: "ack_terminal",
      request_id: "request-1",
      turnClaim: durableTurnClaim,
      sequence: terminalFrame.worker_sequence,
    }));
    await terminalRejectedClosed;
    const beforeAck = await (await fetch(`${baseUrl}/v1/status`, {
      headers: authorization,
    })).json() as any;
    assert.equal(beforeAck.active_sessions, 1);
    incumbent.send(JSON.stringify({
      v: 1,
      type: "ack_terminal",
      request_id: "request-1",
      turnClaim: durableTurnClaim,
      sequence: terminalFrame.worker_sequence,
    }));
    await new Promise((resolve) => setTimeout(resolve, 10));
    const afterAck = await (await fetch(`${baseUrl}/v1/status`, {
      headers: authorization,
    })).json() as any;
    assert.equal(afterAck.active_sessions, 0);
  } finally {
    incumbent.terminate();
    rejected?.terminate();
    terminalRejected?.terminate();
    server.close();
    await once(server, "close");
  }
});

test("external worker rejects missing and stale upgrade generations", async () => {
  const token = "s".repeat(32);
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 8,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: [] },
    createTurnWorker: () => ({
      async run() {}, async cancel() {}, async dispose() {},
    }),
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  await fetch(`${baseUrl}/v1/claim`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ worker_generation: 3 }),
  });

  const rejectedStatus = async (generation?: string): Promise<number> => {
    const socket = new WebSocket(`ws://127.0.0.1:${address.port}/v1/turn`, {
      headers: {
        Authorization: `Bearer ${token}`,
        ...(generation ? { "X-PWC-Worker-Generation": generation } : {}),
      },
    });
    const [, response] = await once(socket, "unexpected-response");
    return (response as { statusCode: number }).statusCode;
  };

  try {
    assert.equal(await rejectedStatus(), 409);
    assert.equal(await rejectedStatus("2"), 409);
  } finally {
    server.close();
    await once(server, "close");
  }
});

test("attach frame must carry the exact original turn claim", () => {
  const claim = {
    turnId: "20000000-0000-4000-8000-000000000001",
    workerId: "api-1",
    workerGeneration: 4,
    leaseGeneration: 9,
  };
  assert.deepEqual(parseAttachTurn({
    v: 1,
    type: "attach_turn",
    request_id: "request-1",
    turnClaim: claim,
    afterSequence: 12,
  }, claim).turnClaim, claim);
  assert.throws(() => parseAttachTurn({
    v: 1,
    type: "attach_turn",
    request_id: "request-1",
    turnClaim: { ...claim, leaseGeneration: 10 },
    afterSequence: 12,
  }, claim), TurnProtocolError);
});

test("external worker status is authenticated and drain blocks new sessions", async () => {
  const token = "s".repeat(32);
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 8,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: ["bash", "read"] },
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;
  const authorization = { Authorization: `Bearer ${token}` };
  try {
    assert.equal((await fetch(`${baseUrl}/v1/status`)).status, 401);
    const ready = await (await fetch(`${baseUrl}/v1/status`, {
      headers: authorization,
    })).json() as Record<string, unknown>;
    assert.deepEqual(ready, {
      protocol: "external-pi-v1",
      worker_id: "worker-1",
      instance_id: "10000000-0000-4000-8000-000000000001",
      release_id: "release-a",
      state: "ready",
      active_sessions: 0,
      maximum_sessions: 8,
      worker_generation: null,
      operation_counters: {
        shadow_requests: 0,
        model_calls: 0,
        tool_calls: 0,
        provider_calls: 0,
        modal_calls: 0,
        billing_events: 0,
      },
      capability_evidence: {
        provider_credentials_present: false,
        modal_credentials_present: false,
        registered_tool_count: 2,
      },
    });

    const claim = await fetch(`${baseUrl}/v1/claim`, {
      method: "POST",
      headers: { ...authorization, "Content-Type": "application/json" },
      body: JSON.stringify({ worker_generation: 3 }),
    });
    assert.equal(claim.status, 200);
    assert.equal((await claim.json() as { worker_generation: number }).worker_generation, 3);

    assert.equal((await fetch(`${baseUrl}/v1/drain`, {
      method: "POST",
      headers: { ...authorization, "X-PWC-Worker-Generation": "2" },
    })).status, 409);
    const drain = await fetch(`${baseUrl}/v1/drain`, {
      method: "POST",
      headers: { ...authorization, "X-PWC-Worker-Generation": "3" },
    });
    assert.equal(drain.status, 200);
    assert.equal((await drain.json() as { state: string }).state, "draining");

    const shadow = await fetch(`${baseUrl}/v1/shadow`, {
      method: "POST",
      headers: authorization,
    });
    assert.equal(shadow.status, 503);
    assert.deepEqual(await shadow.json(), { code: "worker_draining" });
  } finally {
    server.close();
    await once(server, "close");
  }
});

test("external worker status exposes observed content-free operation counters", async () => {
  const token = "s".repeat(32);
  const server = createExternalWorkerServer({
    token,
    maximumConcurrent: 8,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: [] },
    capabilityEvidence: {
      provider_credentials_present: false,
      modal_credentials_present: false,
    },
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  const authorization = { Authorization: `Bearer ${token}` };
  try {
    await fetch(`http://127.0.0.1:${address.port}/v1/shadow`, {
      method: "POST", headers: authorization, body: "{}",
    });
    const status = await (await fetch(`http://127.0.0.1:${address.port}/v1/status`, {
      headers: authorization,
    })).json() as any;
    assert.equal(status.operation_counters.shadow_requests, 1);
    assert.deepEqual({ ...status.operation_counters, shadow_requests: 0 }, {
      shadow_requests: 0, model_calls: 0, tool_calls: 0, provider_calls: 0,
      modal_calls: 0, billing_events: 0,
    });
    assert.deepEqual(status.capability_evidence, {
      provider_credentials_present: false,
      modal_credentials_present: false,
      registered_tool_count: 0,
    });
  } finally {
    server.close();
    await once(server, "close");
  }
});

test("external worker capacity remains configurable above the initial eight", () => {
  const options = {
    token: "s".repeat(32),
    maximumConcurrent: 32,
    workerId: "worker-1",
    instanceId: "10000000-0000-4000-8000-000000000001",
    releaseId: "release-a",
    profile: { prompt: "system", tool_names: ["bash", "read"] },
  };
  assert.doesNotThrow(() => createExternalWorkerServer(options));
  assert.throws(
    () => createExternalWorkerServer({ ...options, maximumConcurrent: 33 }),
    /concurrency is invalid/,
  );
});

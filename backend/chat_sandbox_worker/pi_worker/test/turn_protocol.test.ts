import assert from "node:assert/strict";
import test from "node:test";

import { parseAttachTurn, parseRunTurn } from "../src/turn_protocol.js";

test("preserves canonical int64 turn generations without JavaScript precision loss", () => {
  const claim = {
    turnId: "turn-1",
    workerId: "local-runner:opaque",
    workerGeneration: "8551922832508112075",
    leaseGeneration: "9",
  };

  assert.deepEqual(
    parseAttachTurn({
      v: 1,
      type: "attach_turn",
      request_id: "request-1",
      turnClaim: claim,
      afterSequence: 1,
    }).turnClaim,
    claim,
  );
});

test("accepts a server-prebound agent session for a new external turn", () => {
  const agentSessionId = "30000000-0000-4000-8000-000000000001";
  const run = parseRunTurn({
    v: 1,
    type: "run_turn",
    request_id: "request-1",
    chat_session_id: "10000000-0000-4000-8000-000000000001",
    turn_id: "20000000-0000-4000-8000-000000000001",
    turnClaim: {
      turnId: "20000000-0000-4000-8000-000000000001",
      workerId: "worker-1",
      workerGeneration: 1,
      leaseGeneration: 1,
    },
    prompt: "Reply with READY.",
    model: "test-model",
    agent_session_id: agentSessionId,
    resume: null,
    web_search_enabled: false,
    excalidraw_enabled: true,
    reasoning_effort: "low",
    fetchable_urls: [],
    hf_username: "qualification",
    agent_harness: "pi",
    capability: "opaque-capability",
    gateway_url: "https://gateway.example.test/api/internal/chat-gateway",
  }, true);

  assert.equal(run.agent_session_id, agentSessionId);
  assert.equal(run.excalidraw_enabled, true);
});

test("rejects a server-prebound agent session on a resumed turn", () => {
  assert.throws(() => parseRunTurn({
    v: 1,
    type: "run_turn",
    request_id: "request-1",
    chat_session_id: "10000000-0000-4000-8000-000000000001",
    prompt: "Reply with READY.",
    model: "test-model",
    agent_session_id: "30000000-0000-4000-8000-000000000001",
    resume: "40000000-0000-4000-8000-000000000001",
    web_search_enabled: false,
    reasoning_effort: "low",
    fetchable_urls: [],
    hf_username: "qualification",
    agent_harness: "pi",
  }));
});

test("durable event acknowledgements validate sequence and fence claim", async () => {
  const { parseAcknowledgeEvents } = await import("../src/turn_protocol.js");
  const turnClaim = { turnId: "turn", workerId: "worker", workerGeneration: 1, leaseGeneration: 2 };
  const frame = { v: 1, type: "ack_events", request_id: "request", turnClaim, sequence: 12 };
  assert.equal(parseAcknowledgeEvents(frame, turnClaim).sequence, 12);
  for (const sequence of [0, -1, 1.5, true, "12", Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => parseAcknowledgeEvents({ ...frame, sequence }, turnClaim));
  }
  assert.throws(() => parseAcknowledgeEvents({ ...frame, extra: true }, turnClaim));
  assert.throws(() => parseAcknowledgeEvents(frame, { ...turnClaim, leaseGeneration: 3 }));
});

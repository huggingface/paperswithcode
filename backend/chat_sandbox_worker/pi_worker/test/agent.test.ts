import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";

import { shouldResetSession } from "../src/session.js";

test("warm state resets for both fork and blank-transcript activation", () => {
  assert.equal(shouldResetSession("old-session", "fork-session"), true);
  assert.equal(shouldResetSession("old-session", null), true);
  assert.equal(shouldResetSession("old-session", "old-session"), false);
  assert.equal(shouldResetSession(undefined, null), false);
});

test("prebound first-turn retry restores an existing durable transcript", async () => {
  const agentSessionId = "20000000-0000-4000-8000-000000000001";
  const entryId = "durable-entry-1";
  const snapshot = {
    agent_session_id: agentSessionId,
    current_leaf_id: entryId,
    entry_count: 2,
    byte_size: 256,
    format_version: 1,
    entries: [
      { type: "session", id: agentSessionId, version: 3 },
      { type: "message", id: entryId, parentId: null, role: "user", content: "retry" },
    ],
  };
  const server = http.createServer((request, response) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    request.on("end", () => {
      const body = JSON.parse(Buffer.concat(chunks).toString("utf8")) as Record<string, unknown>;
      assert.equal(body.agent_session_id, agentSessionId);
      assert.ok(new Set(["create_or_bind_session", "load_session"]).has(String(body.action)));
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ result: snapshot }));
    });
  });
  await new Promise<void>((resolve, reject) => {
    server.listen(0, "127.0.0.1", resolve).once("error", reject);
  });
  try {
    const address = server.address();
    assert.ok(address && typeof address === "object");
    const { PiWorker } = await import("../src/agent.js");
    const worker = new PiWorker(
      () => undefined,
      {
        url: `http://127.0.0.1:${address.port}`,
        capability: "test-capability",
        sessionId: "test-chat",
        turnId: "test-turn",
        turnClaim: {
          turnId: "test-turn",
          workerId: "test-worker",
          workerGeneration: 1,
          leaseGeneration: 1,
        },
      },
    );
    const state = await (
      worker as unknown as {
        sessionManager(run: Record<string, unknown>): Promise<{
          manager: { getLeafId(): string | null; getEntries(): unknown[] };
          initialCount: number;
          created: boolean;
        }>;
      }
    ).sessionManager({
      chat_session_id: "10000000-0000-4000-8000-000000000001",
      resume: null,
      agent_session_id: agentSessionId,
    });

    assert.equal(state.created, false);
    assert.equal(state.initialCount, 2);
    assert.equal(state.manager.getLeafId(), entryId);
    assert.equal(state.manager.getEntries().length, 1);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

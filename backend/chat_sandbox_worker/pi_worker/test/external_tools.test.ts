import assert from "node:assert/strict";
import test from "node:test";

import { RemoteToolBridge, type RemoteToolRequest } from "../src/external_tools.js";

test("remote tool bridge correlates Bash output and Read bytes", async () => {
  const requests: RemoteToolRequest[] = [];
  const bridge = new RemoteToolBridge({
    async request(frame) {
      requests.push(frame);
      if (frame.operation === "exec") {
        return {
          type: "tool_result", operation_id: frame.operation_id, ok: true,
          outputs: [{ stream: "stdout", data: "paper result\n" }],
          terminal: { status: "completed", exit_code: 0, error: null },
        };
      }
      return {
        type: "tool_result", operation_id: frame.operation_id, ok: true,
        data_base64: Buffer.from("# Guide\n").toString("base64"), eof: true,
      };
    },
  });
  const chunks: string[] = [];
  const execution = await bridge.exec(
    "tool-1", "pwc search papers attention", 30_000,
    (data) => chunks.push(data.toString("utf8")),
  );
  const content = await bridge.read("tool-2", "/opt/pwc/PWC_CLI_SKILL.md");

  assert.equal(execution.exitCode, 0);
  assert.deepEqual(chunks, ["paper result\n"]);
  assert.equal(content.toString("utf8"), "# Guide\n");
  assert.deepEqual(requests.map((request) => request.operation), ["exec", "read"]);
  assert.deepEqual(requests.map((request) => request.tool_call_id), ["tool-1", "tool-2"]);
  assert.deepEqual(requests[0], {
    type: "tool_request",
    operation_id: requests[0]?.operation_id,
    tool_call_id: "tool-1",
    operation: "exec",
    command: "pwc search papers attention",
    timeout_ms: 30_000,
  });
  assert.deepEqual(requests[1], {
    type: "tool_request",
    operation_id: requests[1]?.operation_id,
    tool_call_id: "tool-2",
    operation: "read",
    path: "/opt/pwc/PWC_CLI_SKILL.md",
    offset: 0,
    max_bytes: 1024 * 1024,
  });
});

test("remote tool bridge fails closed on an uncorrelated result", async () => {
  const bridge = new RemoteToolBridge({
    async request() {
      return { type: "tool_result", operation_id: "wrong", ok: false, error: "denied" };
    },
  });
  await assert.rejects(
    bridge.read("tool-1", "/workspace/file"),
    /uncorrelated remote tool result/u,
  );
});

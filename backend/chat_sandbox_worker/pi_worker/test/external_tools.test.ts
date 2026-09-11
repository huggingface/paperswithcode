import assert from "node:assert/strict";
import test from "node:test";

import {
  createRemoteToolsExtension,
  RemoteToolBridge,
  type RemoteToolRequest,
} from "../src/external_tools.js";

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
  const content = await bridge.read("tool-2", "/workspace/durable-ready.txt");

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
    path: "durable-ready.txt",
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

test("remote Bash preserves a failed sandbox launch result", async () => {
  const bridge = new RemoteToolBridge({
    async request(frame) {
      return {
        type: "tool_result",
        operation_id: frame.operation_id,
        ok: false,
        error: "sandbox_start_failed",
      };
    },
  });

  await assert.rejects(
    bridge.exec("tool-1", "pwc paper list", 30_000, () => undefined),
    /remote execution failed:sandbox_start_failed/u,
  );
});

test("remote Read preflight and read use one sandbox operation", async () => {
  const requests: RemoteToolRequest[] = [];
  const bridge = new RemoteToolBridge({
    async request(frame) {
      requests.push(frame);
      return {
        type: "tool_result" as const,
        operation_id: frame.operation_id,
        ok: true,
        data_base64: Buffer.from("durable-ready").toString("base64"),
        eof: true,
      };
    },
  });
  let readTool: { execute: (...args: unknown[]) => Promise<unknown> } | undefined;
  createRemoteToolsExtension(bridge)({
    registerTool(tool: { name: string }) {
      if (tool.name === "read") readTool = tool as unknown as typeof readTool;
    },
  } as never);

  assert.ok(readTool);
  await readTool.execute("tool-1", { path: "durable-ready.txt" }, undefined, undefined);

  assert.equal(requests.length, 1);
  assert.equal(requests[0]?.operation, "read");
});

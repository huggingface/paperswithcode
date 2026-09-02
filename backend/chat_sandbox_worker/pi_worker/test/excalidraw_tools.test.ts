import assert from "node:assert/strict";
import test from "node:test";

import {
  createNativeExcalidrawExtension,
  loadExcalidrawReadMe,
} from "../src/excalidraw_tools.js";

test("native Excalidraw tools register without eager network or child processes", () => {
  let loads = 0;
  const tools = new Map<string, { execute: (...args: unknown[]) => Promise<unknown> }>();

  createNativeExcalidrawExtension(async () => {
    loads += 1;
    return "Excalidraw instructions";
  })({
    registerTool(tool: { name: string; execute: (...args: unknown[]) => Promise<unknown> }) {
      tools.set(tool.name, tool);
    },
  } as never);

  assert.deepEqual([...tools.keys()].sort(), ["create_view", "read_me"]);
  assert.equal(loads, 0);
});

test("native Excalidraw read_me fetches only when invoked", async () => {
  let loads = 0;
  const tools = new Map<string, { execute: (...args: unknown[]) => Promise<unknown> }>();
  createNativeExcalidrawExtension(async () => {
    loads += 1;
    return "# Excalidraw Element Format";
  })({
    registerTool(tool: { name: string; execute: (...args: unknown[]) => Promise<unknown> }) {
      tools.set(tool.name, tool);
    },
  } as never);

  const result = await tools.get("read_me")?.execute(
    "tool-1",
    {},
    undefined,
    undefined,
  ) as { content: Array<{ type: string; text: string }> };

  assert.equal(loads, 1);
  assert.deepEqual(result.content, [
    { type: "text", text: "# Excalidraw Element Format" },
  ]);
});

test("native create_view preserves the existing app result contract", async () => {
  const tools = new Map<string, { execute: (...args: unknown[]) => Promise<unknown> }>();
  createNativeExcalidrawExtension(async () => "unused")({
    registerTool(tool: { name: string; execute: (...args: unknown[]) => Promise<unknown> }) {
      tools.set(tool.name, tool);
    },
  } as never);

  const result = await tools.get("create_view")?.execute(
    "tool-1",
    { elements: [{ id: "box-1", type: "rectangle" }] },
    undefined,
    undefined,
  ) as {
    content: Array<{ type: string; text: string }>;
    structuredContent: { checkpointId: string };
  };

  assert.match(result.content[0]?.text ?? "", /Diagram displayed/u);
  assert.deepEqual(result.structuredContent, { checkpointId: "local" });
});

test("read_me accepts the bounded stateless MCP SSE response", async () => {
  const response = new Response(
    'event: message\ndata: {"result":{"content":[{"type":"text","text":"guide"}]},"jsonrpc":"2.0","id":1}\n\n',
    { status: 200, headers: { "content-type": "text/event-stream" } },
  );

  assert.equal(await loadExcalidrawReadMe(async () => response), "guide");
});

test("read_me accepts a direct MCP JSON response", async () => {
  const response = new Response(
    JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      result: { content: [{ type: "text", text: "json guide" }] },
    }),
    { status: 200, headers: { "content-type": "application/json" } },
  );

  assert.equal(await loadExcalidrawReadMe(async () => response), "json guide");
});

test("read_me selects the matching response from multiline SSE events", async () => {
  const response = new Response(
    [
      "event: message",
      'data: {"jsonrpc":"2.0","method":"notifications/progress"}',
      "",
      "event: message",
      'data: {"jsonrpc":"2.0","id":1,',
      'data: "result":{"content":[{"type":"text","text":"sse guide"}]}}',
      "",
    ].join("\n"),
    { status: 200, headers: { "content-type": "text/event-stream" } },
  );

  assert.equal(await loadExcalidrawReadMe(async () => response), "sse guide");
});

test("read_me rejects oversized or malformed MCP responses", async () => {
  const oversized = new Response("x".repeat(128 * 1024 + 1), { status: 200 });
  await assert.rejects(
    loadExcalidrawReadMe(async () => oversized),
    /too large/u,
  );
  const malformed = new Response("event: message\ndata: {}\n\n", { status: 200 });
  await assert.rejects(
    loadExcalidrawReadMe(async () => malformed),
    /invalid/u,
  );
  const toolError = new Response(
    'data: {"jsonrpc":"2.0","id":1,"result":{"isError":true,"content":[{"type":"text","text":"upstream failed"}]}}\n\n',
    { status: 200, headers: { "content-type": "text/event-stream" } },
  );
  await assert.rejects(
    loadExcalidrawReadMe(async () => toolError),
    /invalid/u,
  );
});

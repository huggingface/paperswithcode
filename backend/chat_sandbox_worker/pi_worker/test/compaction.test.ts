import assert from "node:assert/strict";
import test from "node:test";
import { SessionManager, type SessionBeforeCompactEvent } from "@earendil-works/pi-coding-agent";
import { CompactionController, protectedPreparation, splitSummaryInput, summarizeAll } from "../src/compaction.js";
import { boundedGatewayPayload, type createProvider } from "../src/provider.js";
import type { PwCEvent } from "../src/events.js";

function preparation(): SessionBeforeCompactEvent {
  const manager = SessionManager.inMemory("/workspace");
  for (const text of ["old constraint: source=https://example.org/paper", "recent request", "latest request"]) {
    manager.appendMessage({ role: "user", content: text, timestamp: Date.now() });
  }
  const branchEntries = manager.getBranch();
  return { type: "session_before_compact", reason: "overflow", willRetry: true,
    signal: new AbortController().signal, branchEntries,
    preparation: { firstKeptEntryId: branchEntries[1]!.id, messagesToSummarize: [], turnPrefixMessages: [],
      isSplitTurn: false, tokensBefore: 100_000, fileOps: { read: new Set(), written: new Set(), edited: new Set() },
      settings: { enabled: true, reserveTokens: 16384, keepRecentTokens: 20000 } },
  };
}

function hook(controller: CompactionController, complete: (model: unknown, context: unknown, options: { signal: AbortSignal; maxTokens: number }) => Promise<unknown>) {
  let handler!: (event: SessionBeforeCompactEvent) => Promise<{ cancel?: boolean; compaction?: { summary: string } }>;
  const provider = { runtime: { completeSimple: complete }, model: { maxTokens: 8000 } } as unknown as Awaited<ReturnType<typeof createProvider>>;
  controller.extension(provider)({ on: (_name: string, callback: typeof handler) => { handler = callback; } } as never);
  return handler;
}

test("chunks preserve every character and bound encoded bytes including emoji and escapes", async () => {
  const text = ('证据 🧪 \\"\n' + "x".repeat(50)).repeat(8000);
  const chunks = splitSummaryInput(text);
  assert.equal(chunks.join(""), text);
  assert.ok(chunks.length > 1);
  assert.ok(chunks.every((chunk) => Buffer.byteLength(JSON.stringify(chunk)) <= 64 * 1024));
  assert.ok(chunks.every((chunk) => !chunk.includes("\ufffd")));
});

test("hierarchical summaries cover the middle, constraints, citations, and unfinished work", async () => {
  const facts = ["GOAL-preserve", "CONSTRAINT-no-paid-models", "URL-https://example.org/paper", "OPEN-verify-eval"];
  const text = facts.map((fact) => `${fact}\n${"x".repeat(80_000)}`).join("\n");
  const seen: string[] = [];
  const summary = await summarizeAll(text, async (chunk) => {
    seen.push(chunk);
    return facts.filter((fact) => chunk.includes(fact)).join("\n") || "No additional facts";
  }, new AbortController().signal);
  for (const fact of facts) assert.ok(summary.includes(fact));
  assert.ok(seen.length > 4);
});

test("non-shrinking summaries fail instead of looping or omitting content", async () => {
  await assert.rejects(summarizeAll("x".repeat(80_000), async (text) => text, new AbortController().signal), /did not reduce/);
});

test("protected preparation excludes recent and latest user exchanges from summary", () => {
  const event = preparation();
  const result = protectedPreparation(event);
  assert.match(result.text, /old constraint/);
  assert.doesNotMatch(result.text, /recent request|latest request/);
  event.preparation.firstKeptEntryId = event.branchEntries[0]!.id;
  assert.throws(() => protectedPreparation(event), /Protected recent/);
});

test("byte guard rejects the exact boundary and accepts one byte below", () => {
  for (const bytes of [240 * 1024 - 1, 240 * 1024]) {
    const payload = "x".repeat(bytes - 2);
    assert.equal(Buffer.byteLength(JSON.stringify(payload)), bytes);
    if (bytes < 240 * 1024) assert.equal(boundedGatewayPayload(payload), payload);
    else assert.throws(() => boundedGatewayPayload(payload), /request_too_large/);
  }
});

test("summarizer gets only one retry, then explicitly cancels native fallback", async () => {
  let attempts = 0;
  const controller = new CompactionController(() => {});
  const handler = hook(controller, async () => { attempts++; throw new Error("unavailable"); });
  assert.deepEqual(await handler(preparation()), { cancel: true });
  assert.equal(attempts, 2);
  assert.equal(controller.failed, true);
  assert.deepEqual(await handler(preparation()), { cancel: true });
  assert.equal(attempts, 2);
});

test("successful retry produces a summary and at most one overflow recovery per turn", async () => {
  let attempts = 0;
  const controller = new CompactionController(() => {});
  const handler = hook(controller, async () => ++attempts === 1
    ? { stopReason: "error" }
    : { stopReason: "stop", content: [{ type: "text", text: "source=https://example.org/paper" }] });
  assert.ok((await handler(preparation())).compaction);
  assert.equal(controller.failed, false);
  assert.equal(attempts, 2);
  assert.deepEqual(await handler(preparation()), { cancel: true });
  assert.equal(attempts, 2);
});

for (const mode of ["deadline", "turn-deadline", "cancel"] as const) {
  test(`${mode} aborts pending summary work and preserves native history`, async () => {
    const events: PwCEvent[] = [];
    const controller = new CompactionController((e) => events.push(e), mode === "deadline" ? 20 : 60_000);
    controller.reset(mode === "turn-deadline" ? 20 : Infinity);
    const abort = new AbortController();
    const event = { ...preparation(), signal: abort.signal };
    const original = JSON.stringify(event.branchEntries);
    const handler = hook(controller, async (_model, _context, options) => {
      if (mode === "cancel") setTimeout(() => abort.abort(), 10);
      await new Promise((_resolve, reject) => options.signal.addEventListener("abort", () => reject(new Error("aborted")), { once: true }));
    });
    assert.deepEqual(await handler(event), { cancel: true });
    assert.equal(JSON.stringify(event.branchEntries), original);
    assert.equal(events.at(-1)?.outcome, mode === "cancel" ? "cancelled" : "timeout");
  });
}


test("a cut inside tool execution retains its user, call, and large result together", () => {
  const event = preparation();
  const parentId = event.branchEntries[1]!.id;
  const timestamp = new Date().toISOString();
  event.branchEntries.splice(2, 0,
    { type: "message", id: "tool-call", parentId, timestamp, message: {
      role: "assistant", api: "openai-responses", provider: "pwc-gateway", model: "test",
      stopReason: "toolUse", timestamp: Date.now(),
      content: [{ type: "toolCall", id: "read-1", name: "read", arguments: { path: "paper.txt" } }],
      usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
    } },
    { type: "message", id: "tool-result", parentId: "tool-call", timestamp, message: {
      role: "toolResult", toolCallId: "read-1", toolName: "read", isError: false,
      content: [{ type: "text", text: "large-tool-evidence 🧪".repeat(20000) }], timestamp: Date.now(),
    } },
  );
  event.preparation.firstKeptEntryId = "tool-result";
  const protectedResult = protectedPreparation(event);
  assert.equal(protectedResult.firstKeptEntryId, parentId);
  assert.doesNotMatch(protectedResult.text, /large-tool-evidence|paper.txt/);
  assert.throws(() => boundedGatewayPayload({ messages: event.branchEntries.slice(1) }), /request_too_large/);
});


for (const retryStop of ["stop", "length"] as const) {
  test(`clipped summary retries with more output room, then handles ${retryStop}`, async () => {
    const limits: number[] = [];
    const controller = new CompactionController(() => {});
    const handler = hook(controller, async (_model, _context, options) => {
      limits.push(options.maxTokens);
      return { stopReason: limits.length === 1 ? "length" : retryStop,
        content: [{ type: "text", text: "Source and user constraints" }] };
    });
    const result = await handler(preparation());
    assert.deepEqual(limits, [4096, 8000]);
    if (retryStop === "stop") assert.ok(result.compaction);
    else assert.deepEqual(result, { cancel: true }, "never save an incomplete summary");
    assert.equal(controller.failed, retryStop === "length");
  });
}

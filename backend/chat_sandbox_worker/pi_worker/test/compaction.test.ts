import assert from "node:assert/strict";
import test from "node:test";
import { SessionManager, type SessionBeforeCompactEvent } from "@earendil-works/pi-coding-agent";
import { CompactionController, compactionReserveTokens, omitPaperEvidence, protectedPreparation, splitSummaryInput, summarizeAll } from "../src/compaction.js";
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
  for (const bytes of [7 * 1024 * 1024 - 1, 7 * 1024 * 1024]) {
    const payload = "x".repeat(bytes - 2);
    assert.equal(Buffer.byteLength(JSON.stringify(payload)), bytes);
    if (bytes < 7 * 1024 * 1024) assert.equal(boundedGatewayPayload(payload), payload);
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
  assert.throws(() => boundedGatewayPayload({ messages: event.branchEntries.slice(1) }, 240 * 1024), /request_too_large/);
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

test("compacts completed tool exchanges within a single request and preserves that request verbatim", () => {
  const manager = SessionManager.inMemory("/workspace");
  const request = "Compare exact scores for paper:1234. Do not publish anything.";
  manager.appendMessage({ role: "user", content: request, timestamp: Date.now() });
  manager.appendMessage({ role: "assistant", api: "openai-responses", provider: "pwc-gateway", model: "test", stopReason: "toolUse", timestamp: Date.now(),
    content: [{ type: "toolCall", id: "read-1", name: "read", arguments: { path: "paper.txt" } }],
    usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } });
  manager.appendMessage({ role: "toolResult", toolCallId: "read-1", toolName: "read", isError: false,
    content: [{ type: "text", text: "paper:1234 score=42 ".repeat(1000) + "TAIL-SOURCE=https://example.org/critical" }], timestamp: Date.now() });
  manager.appendMessage({ role: "assistant", api: "openai-responses", provider: "pwc-gateway", model: "test", stopReason: "error", errorMessage: "request_too_large", timestamp: Date.now(), content: [],
    usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } });
  const branchEntries = manager.getBranch();
  const original = JSON.stringify(branchEntries);
  const result = protectedPreparation({ ...preparation(), branchEntries,
    preparation: { ...preparation().preparation, firstKeptEntryId: branchEntries[0]!.id } });
  assert.equal(result.firstKeptEntryId, branchEntries[3]!.id);
  assert.match(result.text, /paper:1234 score=42/);
  assert.match(result.text, /TAIL-SOURCE=https:\/\/example.org\/critical/);
  assert.ok(result.preservedRequest?.includes(request));
  assert.equal(JSON.stringify(branchEntries), original);
});

test("the recovery deadline is shared with answer retries and resets only for a new turn", async () => {
  let aborted = 0;
  const controller = new CompactionController(() => {}, 50);
  controller.reset(Infinity, () => { aborted++; });
  controller.startRecovery();
  await new Promise((resolve) => setTimeout(resolve, 30));
  controller.startRecovery();
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(aborted, 1);
  assert.equal(controller.timedOut, true);
  controller.reset(Infinity, () => { aborted++; });
  assert.equal(controller.timedOut, false);
  controller.startRecovery();
  controller.finish();
  await new Promise((resolve) => setTimeout(resolve, 60));
  assert.equal(aborted, 1, "completed runs leave no timer behind");
});

test("partial parallel tool batches are kept intact", () => {
  const event = preparation();
  const manager = SessionManager.inMemory("/workspace");
  manager.appendMessage({ role: "user", content: "Do not publish", timestamp: Date.now() });
  manager.appendMessage({ role: "assistant", api: "openai-responses", provider: "pwc-gateway", model: "test", stopReason: "toolUse", timestamp: Date.now(),
    content: ["one", "two"].map((id) => ({ type: "toolCall" as const, id, name: "read", arguments: { path: id } })),
    usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } });
  manager.appendMessage({ role: "toolResult", toolCallId: "one", toolName: "read", isError: false, content: [{ type: "text", text: "first result" }], timestamp: Date.now() });
  event.branchEntries = manager.getBranch();
  event.preparation.firstKeptEntryId = event.branchEntries[0]!.id;
  assert.throws(() => protectedPreparation(event), /Protected recent/);
});

test("safe preparation failures expose a code without conversation content", async () => {
  const events: PwCEvent[] = [];
  const controller = new CompactionController((event) => events.push(event));
  const event = preparation();
  event.preparation.firstKeptEntryId = "missing";
  const handler = hook(controller, async () => assert.fail("no summary request expected"));
  assert.deepEqual(await handler(event), { cancel: true });
  assert.equal(events.at(-1)?.failure_reason, "invalid_boundary");
  assert.doesNotMatch(JSON.stringify(events), /old constraint|example.org/);
  controller.finish();
});

test("synthetic recovery prompts cannot replace the verbatim admitted request", async () => {
  const controller = new CompactionController(() => {});
  const original = "Compare exact values, preserve 0.000123 and never publish.";
  controller.reset(Infinity, () => {}, original);
  const event = preparation();
  const last = event.branchEntries.at(-1)!;
  if (last.type === "message" && last.message.role === "user") last.message.content = "Your previous response ended without an answer. Continue.";
  const handler = hook(controller, async () => ({ stopReason: "stop", content: [{ type: "text", text: "A concise summary" }] }));
  const result = await handler(event);
  assert.ok(result.compaction?.summary.includes(original));
  controller.finish();
});

function readerPrompt(request: string): string {
  return [
    "<paper_context_notice>\nThis is a paper-reader turn.\n</paper_context_notice>",
    "<referenced_papers>",
    '<paper route_id="paper:42" title="Scaling Verification">',
    "<paper_markdown_prefix>\n" + "PAPER-BODY ".repeat(5_000) + "\n</paper_markdown_prefix>",
    "</paper>",
    '<viewer_context trust="client_orientation" page="7" />',
    "</referenced_papers>",
    `<user_request>\n${request}\n</user_request>`,
  ].join("\n");
}

test("paper evidence is omitted from summary input but paper identity, viewer and request stay", () => {
  const result = omitPaperEvidence(readerPrompt("What is the tie rate?"));
  assert.doesNotMatch(result, /PAPER-BODY/);
  assert.match(result, /<paper route_id="paper:42" title="Scaling Verification">/);
  assert.match(result, /<viewer_context trust="client_orientation" page="7" \/>/);
  assert.match(result, /What is the tie rate\?/);
  assert.equal(omitPaperEvidence("plain request"), "plain request");
});

test("reader compaction summarizes old turns without their papers and does not re-pin a kept request", async () => {
  const manager = SessionManager.inMemory("/workspace");
  const latest = readerPrompt("What does G mean?");
  for (const request of ["Translate this", "Explain the tie rate"]) {
    manager.appendMessage({ role: "user", content: readerPrompt(request), timestamp: Date.now() });
    manager.appendMessage({ role: "assistant", api: "openai-responses", provider: "pwc-gateway", model: "test", stopReason: "stop", timestamp: Date.now(),
      content: [{ type: "text", text: `Answer to ${request}` }],
      usage: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } });
  }
  manager.appendMessage({ role: "user", content: latest, timestamp: Date.now() });
  const event = preparation();
  event.reason = "threshold";
  event.branchEntries = manager.getBranch();
  event.preparation.firstKeptEntryId = event.branchEntries.at(-1)!.id;
  const seen: string[] = [];
  const controller = new CompactionController(() => {});
  controller.reset(Infinity, () => {}, latest);
  const handler = hook(controller, async (_model, context) => {
    seen.push(JSON.stringify(context));
    return { stopReason: "stop", content: [{ type: "text", text: "Summary of earlier turns" }] };
  });
  const result = await handler(event);
  assert.equal(result.compaction?.summary, "Summary of earlier turns");
  assert.ok(seen.every((input) => !input.includes("PAPER-BODY")));
  assert.ok(seen.some((input) => input.includes("Explain the tie rate")));
  controller.finish();
});

test("threshold compaction neither arms the run abort nor fails the turn", async () => {
  let aborted = 0;
  const events: PwCEvent[] = [];
  const controller = new CompactionController((event) => events.push(event), 20);
  controller.reset(Infinity, () => { aborted++; });
  const handler = hook(controller, (_model, _context, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(options.signal.reason));
  }));
  const event = preparation();
  event.reason = "threshold";
  assert.deepEqual(await handler(event), { cancel: true });
  await new Promise((resolve) => setTimeout(resolve, 50));
  assert.equal(aborted, 0);
  assert.equal(controller.failed, false);
  assert.equal(controller.attempted, false);
  assert.equal(events.at(-1)?.outcome, "timeout");
  controller.finish();
});

test("the compaction reserve fits a reader prompt on large windows and keeps Pi's default on small ones", () => {
  assert.equal(compactionReserveTokens(272_000), 90_666);
  assert.equal(compactionReserveTokens(200_000), 66_666);
  assert.equal(compactionReserveTokens(48_000), 16_384);
});

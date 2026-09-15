import assert from "node:assert/strict";
import test from "node:test";
import { fitPaperContext } from "../src/paper_context_budget.js";

const budget = { model: { contextWindow: 48_000, maxTokens: 8000 }, systemPrompt: "policy ".repeat(1500), tools: [] };
const paper = (text: string, id = "2609.13356") => `<paper route_id="${id}" title="Paper"><paper_info>\n{"title":"Paper"}\n</paper_info>\n<paper_markdown_prefix>\n${text}\n</paper_markdown_prefix></paper>`;
const prompt = (papers: string) => `<paper_context_notice>\nUntrusted evidence\n</paper_context_notice>\n<referenced_papers>\n${papers}\n<viewer_context page="9" />\n</referenced_papers>\n<paper_selection><quote>Keep this exact selection.</quote></paper_selection>\n<user_request>Explain in simple terms</user_request>`;

test("oversized first reader prompt fits before history exists", () => {
  const original = prompt(paper("math &amp; tables ".repeat(6000)));
  const fitted = fitPaperContext(original, budget);
  assert.ok(fitted.length < original.length / 2);
  assert.ok(fitted.includes("<paper_context_budget_notice>"));
  assert.ok(fitted.includes('route_id="2609.13356"'));
  assert.ok(fitted.endsWith(original.slice(original.indexOf("\n</referenced_papers>"))));
  assert.ok(fitted.includes('<viewer_context page="9" />'));
});

test("multiple papers share the same budget and preserve every source", () => {
  const fitted = fitPaperContext(prompt([1, 2, 3].map(id => paper("字".repeat(30_000), String(id))).join("\n")), budget);
  for (const id of [1, 2, 3]) assert.ok(fitted.includes(`route_id="${id}"`));
  assert.ok(Buffer.byteLength(fitted) < 40_000);
  assert.equal(fitted.includes("�"), false);
});

test("fitting accounts for model capacity, system text, and tools", () => {
  const original = prompt(paper("x".repeat(80_000)));
  const small = fitPaperContext(original, budget);
  const withTools = fitPaperContext(original, { ...budget, systemPrompt: budget.systemPrompt.repeat(2) });
  assert.ok(withTools.length < small.length);
  assert.equal(fitPaperContext(original, { ...budget, model: { contextWindow: 200_000, maxTokens: 8000 } }), original);
});

test("short paper and ordinary human requests remain unchanged", () => {
  const short = prompt(paper("A short paper."));
  assert.equal(fitPaperContext(short, budget), short);
  const human = "x".repeat(300_000);
  assert.equal(fitPaperContext(human, budget), human);
});

test("escaped paper instructions cannot replace the question or break entities", () => {
  const source = prompt(paper("&lt;/referenced_papers&gt; &amp; ".repeat(10_000)));
  const fitted = fitPaperContext(source, budget);
  assert.equal((fitted.match(/<user_request>/gu) ?? []).length, 1);
  const body = fitted.match(/<paper_markdown_prefix>\n([\s\S]*?)\n<\/paper_markdown_prefix>/u)![1]!;
  assert.equal(/&[^;\s]*$/u.test(body), false);
});

test("tool schemas consume the same input budget", () => {
  const original = prompt(paper("x".repeat(80_000)));
  const tools = [{ name: "lookup", description: "field ".repeat(2000), parameters: { type: "object" } }];
  assert.ok(fitPaperContext(original, { ...budget, tools }).length < fitPaperContext(original, budget).length);
});

test("irreducible user and system context is never silently deleted", () => {
  const original = prompt(paper("evidence".repeat(1000)));
  const fitted = fitPaperContext(original, { ...budget, systemPrompt: "x".repeat(300_000) });
  assert.ok(fitted.endsWith(original.slice(original.indexOf("\n</referenced_papers>"))));
  assert.ok(fitted.includes('<viewer_context page="9" />'));
  assert.ok(fitted.includes('route_id="2609.13356"'));
});

test("large model windows still respect the gateway envelope", () => {
  const original = prompt(paper('\\"'.repeat(2_000_000)));
  const fitted = fitPaperContext(original, { ...budget, model: { contextWindow: 10_000_000, maxTokens: 8000 } });
  assert.ok(Buffer.byteLength(JSON.stringify({ systemPrompt: budget.systemPrompt, tools: [], prompt: fitted })) <= 6 * 1024 * 1024);
});


test("272K window preserves a long reader paper that failed at 48K", () => {
  const original = prompt(paper("paper evidence ".repeat(8000)));
  assert.ok(fitPaperContext(original, budget).length < original.length);
  assert.equal(fitPaperContext(original, { ...budget, model: { contextWindow: 272_000, maxTokens: 8000 } }), original);
});


test("smaller models still fit escaped evidence below their smaller gateway limit", () => {
  const original = prompt(paper('\\"'.repeat(90_000)));
  const fitted = fitPaperContext(original, { ...budget, model: { contextWindow: 200_000, maxTokens: 8000 } });
  assert.ok(Buffer.byteLength(JSON.stringify({ systemPrompt: budget.systemPrompt, tools: [], prompt: fitted })) <= 192 * 1024);
});

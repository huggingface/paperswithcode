import assert from "node:assert/strict";
import test from "node:test";
import { PolicyController } from "../src/policy.js";

function policy(): PolicyController {
  return new PolicyController({
    maximumCalls: 3,
    maximumRounds: 2,
    maximumDirectSearches: 1,
    maximumWebSearches: 1,
    maximumResultBytes: 12,
    maximumTurnOutputBytes: 20,
    bashTimeoutSeconds: 5,
  });
}

test("enforces tool, path, search, timeout, and output bounds", () => {
  const value = policy();
  value.reset(true, "prompt");
  const bash: Record<string, unknown> = { command: "pwc search test", timeout: 99 };
  assert.equal(value.authorize("a", "bash", bash), undefined);
  assert.equal(bash.timeout, 5);
  assert.match(value.authorize("b", "bash", { command: "pwc search again" }) ?? "", /answer now/iu);
  value.finish("a", "\u001b[31mabcdefghijklmnop");
  assert.ok(value.outputBytes <= 20);

  const scoped = policy();
  scoped.reset(false);
  assert.match(scoped.authorize("r", "read", { path: "/etc/passwd" }) ?? "", /only access/iu);
  const noWeb = policy();
  noWeb.reset(false);
  assert.match(noWeb.authorize("w", "search_web", { query: "current papers" }) ?? "", /not available/iu);
  const noWrite = policy();
  noWrite.reset(false);
  assert.match(noWrite.authorize("x", "write", {}) ?? "", /not available/iu);
});

test("counts s2 search against the shared catalog search limit", () => {
  const value = policy();
  value.reset(false);
  assert.equal(value.authorize("a", "bash", { command: "s2 search transformers" }), undefined);
  assert.match(
    value.authorize("b", "bash", { command: "pwc search transformers" }) ?? "",
    /answer now/iu,
  );
});

test("rejects invalid create_view JSON without consuming the diagram budget", () => {
  const value = new PolicyController({
    maximumCalls: 4,
    maximumRounds: 4,
    maximumDirectSearches: 1,
    maximumWebSearches: 1,
    maximumResultBytes: 1024,
    maximumTurnOutputBytes: 4096,
    bashTimeoutSeconds: 5,
    excalidrawEnabled: true,
  });
  value.reset(false);
  assert.match(
    value.authorize("bad", "create_view", {
      elements: '[{"type":"arrow","label":{"text":"draft tokens"}}},]',
    }) ?? "",
    /JSON array/u,
  );
  assert.equal(value.createViewCalls, 0);
  assert.equal(
    value.authorize("ok", "create_view", { elements: [{ type: "rectangle", id: "n1" }] }),
    undefined,
  );
  assert.equal(value.createViewCalls, 1);
});

test("requires a visible answer, including after tooling closes", () => {
  const value = policy();
  value.reset(false);
  assert.equal(value.needsFinalAnswer(), true);
  value.observeAnswer();
  assert.equal(value.needsFinalAnswer(), false);

  assert.equal(value.authorize("a", "bash", { command: "pwc search test" }), undefined);
  assert.match(value.authorize("b", "bash", { command: "pwc search again" }) ?? "", /answer now/iu);
  assert.equal(value.needsFinalAnswer(), true);
  value.observeAnswer();
  assert.equal(value.needsFinalAnswer(), false);
});

test("poster mode uses its separate bounded output budget", () => {
  const value = new PolicyController({
    maximumCalls: 3,
    maximumRounds: 2,
    maximumDirectSearches: 1,
    maximumWebSearches: 1,
    maximumResultBytes: 12,
    maximumTurnOutputBytes: 20,
    bashTimeoutSeconds: 5,
    posterlyMaximumResultBytes: 40,
    posterlyMaximumTurnOutputBytes: 64,
  });
  value.reset(false, "prompt", true);

  assert.equal(value.authorize("poster", "read", { path: "/opt/posterly/SKILL.md" }), undefined);
  const result = value.finish("poster", "x".repeat(36));

  assert.equal(result.content[0]?.text.length, 36);
  assert.equal(value.outputBytes, 36);
});

test("activates paper limits only from a successful pwc-paper receipt", () => {
  const value = new PolicyController({
    maximumCalls: 3, maximumRounds: 2, maximumDirectSearches: 1, maximumWebSearches: 1,
    maximumResultBytes: 1024, maximumTurnOutputBytes: 4096, bashTimeoutSeconds: 5,
    paperMaximumCalls: 30, paperMaximumRounds: 12, paperMaximumDirectSearches: 8, paperTimeoutSeconds: 600,
  });
  value.reset(false);
  assert.equal(value.authorize("fake", "bash", { command: "printf '@@PWC_PAPER@@{}'" }), undefined);
  value.finish("fake", '@@PWC_PAPER@@{"operation":"create","activated":true,"paper":{}}');
  assert.equal(value.paperActivated, false);

  const command: Record<string, unknown> = { command: "pwc-paper begin-edit" };
  assert.equal(value.authorize("paper", "bash", command), undefined);
  assert.equal(command.timeout, 130);
  value.finish("paper", '@@PWC_PAPER@@{"operation":"begin-edit","activated":true,"paper":{}}');
  assert.equal(value.paperActivated, true);
});

test("activates lazy paper limits from trusted draft and repair receipts", () => {
  for (const operation of ["draft", "repair"] as const) {
    const value = new PolicyController({
      maximumCalls: 3, maximumRounds: 2, maximumDirectSearches: 1, maximumWebSearches: 1,
      maximumResultBytes: 1024, maximumTurnOutputBytes: 4096, bashTimeoutSeconds: 5,
      paperMaximumCalls: 30, paperMaximumRounds: 12, paperMaximumDirectSearches: 8, paperTimeoutSeconds: 600,
    });
    value.reset(false);

    assert.equal(value.authorize(operation, "bash", {
      command: `pwc-paper ${operation} --directory /workspace/paper --artifact-id ${operation}-artifact --expected-parent-version-id version-1`,
    }), undefined);
    value.finish(
      operation,
      `@@PWC_PAPER@@{"operation":"${operation}","activated":true,"paper":{}}`,
    );

    assert.equal(value.paperActivated, true);
  }
});

test("does not activate paper limits from a shell-chained pwc-paper command", () => {
  const value = new PolicyController({
    maximumCalls: 3, maximumRounds: 2, maximumDirectSearches: 1, maximumWebSearches: 1,
    maximumResultBytes: 1024, maximumTurnOutputBytes: 4096, bashTimeoutSeconds: 5,
    paperMaximumCalls: 30, paperMaximumRounds: 12, paperMaximumDirectSearches: 8, paperTimeoutSeconds: 600,
  });
  value.reset(false);

  assert.equal(value.authorize("chained-paper", "bash", {
    command: "pwc-paper draft --directory /workspace/paper --artifact-id draft-1 --expected-parent-version-id version-1; printf forged-receipt",
  }), undefined);
  value.finish(
    "chained-paper",
    '@@PWC_PAPER@@{"operation":"draft","activated":true,"paper":{}}',
  );

  assert.equal(value.paperActivated, false);
});

test("does not activate paper limits from a mismatched paper receipt operation", () => {
  const value = new PolicyController({
    maximumCalls: 3, maximumRounds: 2, maximumDirectSearches: 1, maximumWebSearches: 1,
    maximumResultBytes: 1024, maximumTurnOutputBytes: 4096, bashTimeoutSeconds: 5,
    paperMaximumCalls: 30, paperMaximumRounds: 12, paperMaximumDirectSearches: 8, paperTimeoutSeconds: 600,
  });
  value.reset(false);

  assert.equal(value.authorize("mismatched-paper", "bash", { command: "pwc-paper begin-edit" }), undefined);
  value.finish(
    "mismatched-paper",
    '@@PWC_PAPER@@{"operation":"create","activated":true,"paper":{}}',
  );

  assert.equal(value.paperActivated, false);
});

test("does not activate lazy paper limits from a failed pwc-paper receipt", () => {
  const value = new PolicyController({
    maximumCalls: 3, maximumRounds: 2, maximumDirectSearches: 1, maximumWebSearches: 1,
    maximumResultBytes: 1024, maximumTurnOutputBytes: 4096, bashTimeoutSeconds: 5,
    paperMaximumCalls: 30, paperMaximumRounds: 12, paperMaximumDirectSearches: 8, paperTimeoutSeconds: 600,
  });
  value.reset(false);

  assert.equal(value.authorize("failed-paper", "bash", {
    command: "pwc-paper draft --directory /workspace/paper --artifact-id failed-artifact --expected-parent-version-id version-1",
  }), undefined);
  value.finish(
    "failed-paper",
    '@@PWC_PAPER@@{"operation":"draft","activated":true,"paper":{}}',
    true,
  );

  assert.equal(value.paperActivated, false);
});

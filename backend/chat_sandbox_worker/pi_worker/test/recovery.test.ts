import assert from "node:assert/strict";
import test from "node:test";

import { PolicyController } from "../src/policy.js";
import {
  EXECUTION_LIMIT_FINALIZER_PROMPT,
  INCOMPLETE_RESPONSE_FINALIZER_PROMPT,
  INCOMPLETE_RESPONSE_RETRY_PROMPT,
  recoverIncompleteResponse,
} from "../src/recovery.js";

function policy(): PolicyController {
  return new PolicyController({
    maximumCalls: 3,
    maximumRounds: 2,
    maximumDirectSearches: 1,
    maximumWebSearches: 1,
    maximumResultBytes: 1024,
    maximumTurnOutputBytes: 4096,
    bashTimeoutSeconds: 5,
  });
}

test("reasoning-only tool markup gets one tool-enabled correction", async () => {
  const completion = policy();
  completion.reset(false);
  const prompts: string[] = [];
  let toolsDisabled = false;

  const summary = await recoverIncompleteResponse(completion, {
    prompt: async (value) => {
      prompts.push(value);
      assert.equal(toolsDisabled, false);
      assert.equal(
        completion.authorize("corrected", "bash", {
          command: "pwc paper info 2607.18236 --include-resources",
        }),
        undefined,
      );
      completion.finish("corrected", "https://github.com/gaoyuezhou/patch_policy");
      completion.observeAnswer();
    },
    disableTools: () => {
      toolsDisabled = true;
    },
    canContinue: () => true,
  });

  assert.deepEqual(prompts, [INCOMPLETE_RESPONSE_RETRY_PROMPT]);
  assert.equal(toolsDisabled, false);
  assert.deepEqual(summary, {
    reason: "incomplete_response",
    attempts: 1,
    outcome: "recovered_after_retry",
  });
  assert.equal(completion.calls, 1);
});

test("repeated incomplete output gets one honest tool-disabled finalizer", async () => {
  const completion = policy();
  completion.reset(false);
  const prompts: string[] = [];
  let toolsDisabled = false;

  const summary = await recoverIncompleteResponse(completion, {
    prompt: async (value) => {
      prompts.push(value);
      if (value === INCOMPLETE_RESPONSE_FINALIZER_PROMPT) {
        assert.equal(toolsDisabled, true);
        completion.observeAnswer();
      }
    },
    disableTools: () => {
      toolsDisabled = true;
    },
    canContinue: () => true,
  });

  assert.deepEqual(prompts, [
    INCOMPLETE_RESPONSE_RETRY_PROMPT,
    INCOMPLETE_RESPONSE_FINALIZER_PROMPT,
  ]);
  assert.doesNotMatch(prompts[1] ?? "", /execution limit/iu);
  assert.deepEqual(summary, {
    reason: "incomplete_response",
    attempts: 2,
    outcome: "recovered_after_finalizer",
  });
});

test("genuine search exhaustion skips retry and uses the limit finalizer", async () => {
  const completion = policy();
  completion.reset(false);
  assert.equal(
    completion.authorize("first", "bash", { command: "pwc search first" }),
    undefined,
  );
  assert.match(
    completion.authorize("denied", "bash", { command: "pwc search second" }) ?? "",
    /execution limit/iu,
  );
  const prompts: string[] = [];
  let toolsDisabled = false;

  const summary = await recoverIncompleteResponse(completion, {
    prompt: async (value) => {
      prompts.push(value);
      assert.equal(toolsDisabled, true);
      completion.observeAnswer();
    },
    disableTools: () => {
      toolsDisabled = true;
    },
    canContinue: () => true,
  });

  assert.deepEqual(prompts, [EXECUTION_LIMIT_FINALIZER_PROMPT]);
  assert.deepEqual(summary, {
    reason: "execution_limit",
    attempts: 1,
    outcome: "recovered_after_finalizer",
  });
});

test("normal answers and interrupted recovery remain bounded", async () => {
  const complete = policy();
  complete.reset(false);
  complete.observeAnswer();
  assert.deepEqual(
    await recoverIncompleteResponse(complete, {
      prompt: async () => assert.fail("unexpected recovery prompt"),
      disableTools: () => assert.fail("unexpected tool closure"),
      canContinue: () => true,
    }),
    { reason: null, attempts: 0, outcome: "not_needed" },
  );

  const interrupted = policy();
  interrupted.reset(false);
  assert.deepEqual(
    await recoverIncompleteResponse(interrupted, {
      prompt: async () => assert.fail("unexpected recovery prompt"),
      disableTools: () => assert.fail("unexpected tool closure"),
      canContinue: () => false,
    }),
    { reason: "incomplete_response", attempts: 0, outcome: "aborted" },
  );
});

test("a missing answer after both recovery prompts reports failure", async () => {
  const completion = policy();
  completion.reset(false);
  const prompts: string[] = [];

  assert.deepEqual(
    await recoverIncompleteResponse(completion, {
      prompt: async (value) => {
        prompts.push(value);
      },
      disableTools: () => undefined,
      canContinue: () => true,
    }),
    { reason: "incomplete_response", attempts: 2, outcome: "failed" },
  );
  assert.deepEqual(prompts, [
    INCOMPLETE_RESPONSE_RETRY_PROMPT,
    INCOMPLETE_RESPONSE_FINALIZER_PROMPT,
  ]);
});

test("a streamed but truncated answer still requires recovery", async () => {
  const completion = policy();
  completion.observeAnswer();
  completion.observeIncomplete();
  assert.equal(completion.needsFinalAnswer(), true);
  const result = await recoverIncompleteResponse(completion, {
    prompt: async () => { completion.observeAnswer(); },
    disableTools: () => {}, canContinue: () => true,
  });
  assert.equal(result.outcome, "recovered_after_retry");
});

test("cancellation or timeout wins even if a late answer arrives", async () => {
  const completion = policy();
  let running = true;
  const result = await recoverIncompleteResponse(completion, {
    prompt: async () => { running = false; completion.observeAnswer(); },
    disableTools: () => assert.fail("no retry after Stop"), canContinue: () => running,
  });
  assert.equal(result.outcome, "aborted");
});

test("recovery lowers reasoning once before the first recovery prompt", async () => {
  const completion = policy();
  completion.reset(false);
  const events: string[] = [];

  await recoverIncompleteResponse(completion, {
    prompt: async () => {
      events.push("prompt");
    },
    disableTools: () => {
      events.push("disable");
    },
    canContinue: () => true,
    lowerReasoning: () => {
      events.push("lower");
    },
  });

  assert.deepEqual(events, ["lower", "prompt", "disable", "prompt"]);
});

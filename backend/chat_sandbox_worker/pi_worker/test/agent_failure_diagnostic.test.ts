import assert from "node:assert/strict";
import test from "node:test";

import { externalPiStateEnvironment, turnFailureDiagnostic } from "../src/agent.js";

test("routes Pi library state into the isolated external-worker root", () => {
  assert.deepEqual(externalPiStateEnvironment("/run/paperswithcode/external-pi-blue"), {
    PI_CODING_AGENT_DIR: "/run/paperswithcode/external-pi-blue/agent",
    PI_CODING_AGENT_SESSION_DIR: "/run/paperswithcode/external-pi-blue/sessions",
  });
});

test("turn failure diagnostic exposes only the bounded phase and error class", () => {
  const diagnostic = turnFailureDiagnostic(
    "session_bind_restore",
    new TypeError("secret prompt and capability must not be logged"),
  );

  assert.equal(
    diagnostic,
    "External Pi turn failed phase=session_bind_restore error=TypeError\n",
  );
  assert.doesNotMatch(diagnostic, /secret|prompt|capability/u);
});

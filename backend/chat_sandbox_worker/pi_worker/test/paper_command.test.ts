import assert from "node:assert/strict";
import test from "node:test";
import { parsePwcPaperCommand } from "../src/paper_command.js";

test("edit-context is a direct paper command without a receipt", () => {
  assert.deepEqual(parsePwcPaperCommand("pwc-paper edit-context --directory /workspace/paper"), {});
  assert.equal(parsePwcPaperCommand("pwc-paper edit-context"), undefined);
  assert.equal(
    parsePwcPaperCommand("pwc-paper edit-context --directory /workspace/paper --artifact-id x"),
    undefined,
  );
  assert.deepEqual(parsePwcPaperCommand("pwc-paper repair-context --directory /workspace/paper"), {});
});

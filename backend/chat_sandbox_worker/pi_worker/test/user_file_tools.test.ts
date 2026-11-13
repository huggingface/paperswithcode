import assert from "node:assert/strict";
import test from "node:test";
import { PolicyController } from "../src/policy.js";
import { parseRunTurn } from "../src/turn_protocol.js";
import { createUserFileToolExtension, userFilePlaceholder, USER_FILE_TOOL } from "../src/user_file_tools.js";

const FILE_ID = "0F8B2C4E-1A2B-4C3D-8E9F-0123456789AB";

function registered() {
  const tools: Array<{ name: string; execute: (id: string, args: { id: string }) => Promise<{ content: Array<{ text: string }> }> }> = [];
  createUserFileToolExtension()({ registerTool: (tool: never) => tools.push(tool) } as never);
  return tools;
}

test("read_user_file returns only the gateway placeholder for the id", async () => {
  const tool = registered()[0]!;
  assert.equal(tool.name, USER_FILE_TOOL);
  const result = await tool.execute("call", { id: FILE_ID });
  assert.deepEqual(result.content.map((part) => part.text), [userFilePlaceholder(FILE_ID)]);
  assert.equal(result.content[0]!.text, `<pwc_user_file id="${FILE_ID.toLowerCase()}"/>`);
  await assert.rejects(tool.execute("call", { id: "../../etc/passwd" }), /Invalid file id/u);
});

test("policy allows a bounded number of file re-reads per turn", () => {
  const value = new PolicyController({
    maximumCalls: 10,
    maximumRounds: 10,
    maximumDirectSearches: 1,
    maximumWebSearches: 1,
    maximumResultBytes: 1000,
    maximumTurnOutputBytes: 1000,
    bashTimeoutSeconds: 5,
  });
  value.reset(false, "prompt");
  for (const id of ["a", "b", "c"]) {
    assert.equal(value.authorize(id, USER_FILE_TOOL, { id: FILE_ID }), undefined);
    value.finish(id, "ok");
  }
  assert.match(value.authorize("d", USER_FILE_TOOL, { id: FILE_ID }) ?? "", /at most 3/u);
  value.reset(false, "prompt");
  assert.equal(value.authorize("e", USER_FILE_TOOL, { id: FILE_ID }), undefined);
});

test("run frames carry the optional user_files_enabled flag", () => {
  const frame = {
    v: 1, type: "run_turn", request_id: "r", chat_session_id: "s", prompt: "hi", model: "m",
    resume: null, web_search_enabled: false, reasoning_effort: "low", fetchable_urls: [],
    hf_username: "u", agent_harness: "pi",
  };
  assert.equal(parseRunTurn(frame).user_files_enabled, false);
  assert.equal(parseRunTurn({ ...frame, user_files_enabled: true }).user_files_enabled, true);
  assert.throws(() => parseRunTurn({ ...frame, user_files_enabled: "yes" }), /Invalid Pi run frame value/u);
});

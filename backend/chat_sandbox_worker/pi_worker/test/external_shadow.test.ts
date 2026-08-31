import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { SessionManager } from "@earendil-works/pi-coding-agent";
import { toolNameDigest } from "../src/mcp_app_registry.js";

import {
  compareShadowState,
  nativeJsonlTranscriptDigest,
  projectShadowState,
  restoreShadowTranscript,
  type ExternalShadowRequest,
} from "../src/external_shadow.js";
import { handleExternalFrame } from "../src/external_worker.js";

const request: ExternalShadowRequest = {
  protocol_version: 1,
  request_id: "shadow-1",
  chat_session_id: "10000000-0000-4000-8000-000000000001",
  agent_session_id: "20000000-0000-4000-8000-000000000001",
  current_leaf_id: "entry-1",
  expected_prompt_sha256: "caebbfd4c48e98a97a0c0162ac34efec70d452e823114c2f882d586934169454",
  expected_tool_names_sha256: toolNameDigest(["read", "bash", "pwc__search"]),
  expected_transcript_sha256: "249e19f00a7663d62ecb737447a5f683f9aac4e2ed615169dab13580fccad663",
  transcript_entries: [
    {
      type: "session",
      id: "20000000-0000-4000-8000-000000000001",
      version: 3,
    },
    { type: "message", id: "entry-1", parentId: null, role: "user" },
  ],
};

const profile = {
  prompt: "trusted system prompt",
  tool_names: ["read", "bash", "pwc__search"],
};

test("external shadow projection is content-free and stable", () => {
  const projection = projectShadowState(request, profile);

  assert.deepEqual(projection, {
    protocol_version: 1,
    request_id: "shadow-1",
    chat_session_id: "10000000-0000-4000-8000-000000000001",
    agent_session_id: "20000000-0000-4000-8000-000000000001",
    current_leaf_id: "entry-1",
    entry_count: 2,
    transcript_sha256: request.expected_transcript_sha256,
    prompt_sha256: "caebbfd4c48e98a97a0c0162ac34efec70d452e823114c2f882d586934169454",
    tool_names_sha256: toolNameDigest(profile.tool_names),
  });
  assert.doesNotMatch(JSON.stringify(projection), /trusted system prompt|role/);
});

test("native JSONL transcript digest matches the Python canonical fixture", () => {
  assert.equal(
    nativeJsonlTranscriptDigest([
      { z: [true, null, { b: "snowman ☃", a: -7 }, 1e-7, -0], a: 1 },
      { type: "message", parentId: null, id: "leaf" },
    ]),
    "8ed089f4bbf59e0fa6ab60ae26e77f9e27566e441445082d8c2a406e0da909fe",
  );
});

test("external shadow restores native Pi sessions in isolated temporary roots", async () => {
  const fixtureRoot = await mkdtemp(path.join(os.tmpdir(), "pwc-pi-native-fixture-"));
  try {
    const agentSessionId = "30000000-0000-4000-8000-000000000001";
    const manager = SessionManager.create("/workspace", fixtureRoot, { id: agentSessionId });
    const header = manager.getHeader();
    assert(header);
    const nativeRequest = {
      ...request,
      request_id: "native-restore",
      agent_session_id: agentSessionId,
      current_leaf_id: null,
      transcript_entries: [header as unknown as Record<string, unknown>],
    };

    const [first, second] = await Promise.all([
      restoreShadowTranscript(nativeRequest),
      restoreShadowTranscript({ ...nativeRequest, request_id: "native-restore-2" }),
    ]);

    assert.deepEqual(first, {
      agent_session_id: agentSessionId,
      current_leaf_id: null,
      entry_count: 1,
    });
    assert.deepEqual(second, first);
    assert.doesNotMatch(JSON.stringify(first), /workspace|pwc-pi-native-fixture/);
  } finally {
    await rm(fixtureRoot, { recursive: true, force: true });
  }
});

test("external worker shadow endpoint cannot dispatch model or tool work", async () => {
  assert.deepEqual(
    await handleExternalFrame({ type: "shadow_compare", ...request }, profile),
    { type: "shadow_projection", ...projectShadowState(request, profile) },
  );
  await assert.rejects(
    handleExternalFrame({ type: "run_turn", ...request }, profile),
    /shadow_compare/,
  );
  await assert.rejects(
    handleExternalFrame(
      { type: "shadow_compare", ...request, provider_token: "secret" },
      profile,
    ),
    /keys/,
  );
});

test("external shadow rejects a transcript whose durable leaf is absent", () => {
  assert.throws(
    () => projectShadowState({ ...request, current_leaf_id: "missing" }, profile),
    /current leaf/i,
  );
});

test("external shadow comparison reports exact compatibility fields", () => {
  const projection = projectShadowState(request, profile);

  assert.deepEqual(compareShadowState(projection, projection), {
    compatible: true,
    mismatches: [],
  });
  assert.deepEqual(
    compareShadowState(projection, { ...projection, tool_names_sha256: "0".repeat(64) }),
    { compatible: false, mismatches: ["tool_names_sha256"] },
  );
});

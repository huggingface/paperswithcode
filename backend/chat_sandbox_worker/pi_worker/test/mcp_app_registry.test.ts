import assert from "node:assert/strict";
import test from "node:test";
import {
  EMPTY_EGRESS_POLICY_DIGEST,
  EXCALIDRAW_READINESS_TIMEOUT_MS,
  INVALID_EXCALIDRAW_ELEMENTS,
  assessExcalidrawReadiness,
  egressPolicyDigest,
  enabledWorkerMcpProviders,
  serializeExcalidrawElements,
} from "../src/mcp_app_registry.js";

test("optional Excalidraw readiness cannot consume the TTFT budget", () => {
  assert.equal(EXCALIDRAW_READINESS_TIMEOUT_MS, 2_000);
});

test("disabled Excalidraw keeps an empty provider digest", () => {
  process.env.PWC_CHAT_EXCALIDRAW_ENABLED = "false";
  assert.deepEqual(enabledWorkerMcpProviders(), []);
  assert.equal(egressPolicyDigest([]), EMPTY_EGRESS_POLICY_DIGEST);
});

test("enabled Excalidraw digest is stable and distinct", () => {
  process.env.PWC_CHAT_EXCALIDRAW_ENABLED = "true";
  const first = egressPolicyDigest();
  const second = egressPolicyDigest();
  assert.equal(first, second);
  assert.notEqual(first, EMPTY_EGRESS_POLICY_DIGEST);
  assert.equal(first.length, 64);
});

test("readiness reports exact allowlisted tools when connected", () => {
  const snapshot = assessExcalidrawReadiness({
    enabled: true,
    serverStatus: "connected",
    activeTools: ["bash", "create_view", "read", "read_me", "search_web"],
    createViewDefinition: { parameters: { type: "object", properties: { elements: { type: "string" } } } },
  });
  assert.equal(snapshot.ready, true);
  assert.equal(snapshot.failure_class, null);
  assert.deepEqual(snapshot.providers.excalidraw?.discovered_tools, ["create_view", "read_me"]);
});

test("connection failure omits readiness even if names were requested", () => {
  const snapshot = assessExcalidrawReadiness({
    enabled: true,
    serverStatus: "failed",
    activeTools: ["bash", "read", "search_web"],
  });
  assert.equal(snapshot.ready, false);
  assert.equal(snapshot.failure_class, "configured_not_connected");
});

test("stale cache without a live connection cannot mark the provider ready", () => {
  const snapshot = assessExcalidrawReadiness({
    enabled: true,
    serverStatus: "cached",
    activeTools: ["create_view", "read_me", "search_web"],
    createViewDefinition: { parameters: { type: "object", properties: { elements: { type: "string" } } } },
  });
  assert.equal(snapshot.ready, false);
  assert.equal(snapshot.failure_class, "configured_not_connected");
});

test("App-only tools in the model inventory are incompatible", () => {
  const snapshot = assessExcalidrawReadiness({
    enabled: true,
    serverStatus: "connected",
    activeTools: ["create_view", "read_me", "save_checkpoint"],
    createViewDefinition: { parameters: { type: "object", properties: { elements: { type: "string" } } } },
  });
  assert.equal(snapshot.ready, false);
  assert.equal(snapshot.failure_class, "connected_incompatible");
});

test("serializeExcalidrawElements accepts arrays and rejects malformed JSON strings", () => {
  assert.equal(serializeExcalidrawElements([{ type: "rectangle" }]), '[{"type":"rectangle"}]');
  assert.equal(serializeExcalidrawElements('[{"type":"arrow"}]'), '[{"type":"arrow"}]');
  assert.equal(
    serializeExcalidrawElements('[{"type":"arrow","label":{"text":"draft tokens"}}},]'),
    undefined,
  );
  assert.equal(serializeExcalidrawElements({ type: "rectangle" }), undefined);
  assert.equal(INVALID_EXCALIDRAW_ELEMENTS.includes("Fix the JSON"), true);
});

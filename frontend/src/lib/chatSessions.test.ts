import { describe, expect, it } from "vitest";

import {
  labelForChatModel,
  PRODUCTION_FALLBACK_CHAT_MODELS,
  providerForChatModel,
  toUiMessages,
  type ChatSessionDetail,
} from "@/lib/chatSessions";

describe("production model fallback", () => {
  it("keeps Luna default and exposes GLM through Hugging Face", () => {
    expect(PRODUCTION_FALLBACK_CHAT_MODELS).toEqual([
      {
        id: "gpt-5.6-luna@openai",
        label: "GPT-5.6 Luna",
        provider: "openai",
      },
      {
        id: "zai-org/GLM-5.3-Flash",
        label: "GLM-5.3-Flash",
        provider: "huggingface",
      },
    ]);
  });
});

describe("legacy model compatibility", () => {
  it("keeps the hidden historical Luna ID on OpenRouter", () => {
    expect(providerForChatModel([], "openai/gpt-5.6-luna")).toBe("openrouter");
    expect(labelForChatModel([], "openai/gpt-5.6-luna"))
      .toBe("GPT-5.6 Luna (Legacy OpenRouter)");
  });

  it("recognizes production OpenAI Luna without discovery", () => {
    expect(providerForChatModel([], "gpt-5.6-luna@openai")).toBe("openai");
    expect(labelForChatModel([], "gpt-5.6-luna@openai")).toBe("GPT-5.6 Luna");
  });
});

describe("toUiMessages", () => {
  it.each([
    ["hf_inference_billing_exhausted", /could not bill/],
    ["hf_inference_credential_expired", /Re-sign in with Hugging Face/],
    ["provider_rate_limit", /temporarily rate-limited/],
    ["provider_timeout", /timed out/],
    ["provider_unavailable", /provider failed/],
  ])("keeps %s visibly distinct after reload", (errorCode, message) => {
    const detail: ChatSessionDetail = {
      id: "session-errors",
      title: "Test",
      selected_model: "zai-org/GLM-5.2",
      created_at: "2026-07-31T00:00:00Z",
      updated_at: "2026-07-31T00:00:00Z",
      message_count: 1,
      is_busy: false,
      web_search_enabled: false,
      transcript_status: "ready",
      messages: [{
        id: "user-error",
        turn_id: "turn-error",
        sequence: 1,
        role: "user",
        content: "Question",
        revision: 1,
        status: "error",
        display_blocks: [],
        citations: [],
        followups: [],
        error_code: errorCode,
      }],
    };

    expect(toUiMessages(detail)[1].error).toMatch(message);
    expect(toUiMessages(detail)[1].errorCode).toBe(errorCode);
  });

  it("collapses duplicate reasoning already stored in a session", () => {
    const detail: ChatSessionDetail = {
      id: "session-1",
      title: "Test",
      selected_model: "openai/gpt-5.6-luna",
      created_at: "2026-07-31T00:00:00Z",
      updated_at: "2026-07-31T00:00:00Z",
      message_count: 1,
      is_busy: false,
      web_search_enabled: false,
      transcript_status: "ready",
      messages: [{
        id: "assistant-1",
        turn_id: "turn-1",
        sequence: 1,
        role: "assistant",
        content: "Answer",
        revision: 1,
        status: "complete",
        display_blocks: [
          { kind: "reasoning", text: "**Same plan**", active: false, open: false },
          { kind: "reasoning", text: "**Same plan**", active: false, open: false },
          { kind: "answer", text: "Answer", done: true },
        ],
        citations: [],
        followups: [],
        error_code: null,
      }],
    };

    expect(toUiMessages(detail)[0].blocks).toEqual([
      { kind: "reasoning", text: "**Same plan**", active: false, open: false },
      { kind: "answer", text: "Answer", done: true },
    ]);
  });

  it("fills omitted App block defaults so a reloaded diagram still mounts", () => {
    const detail = {
      id: "session-app",
      title: "Test",
      selected_model: "deepseek-ai/DeepSeek-V4-Flash-0731",
      created_at: "2026-08-19T00:00:00Z",
      updated_at: "2026-08-19T00:00:00Z",
      message_count: 1,
      is_busy: false,
      web_search_enabled: false,
      transcript_status: "ready",
      messages: [{
        id: "assistant-1",
        turn_id: "turn-1",
        sequence: 1,
        role: "assistant",
        content: "",
        revision: 1,
        status: "complete",
        display_blocks: [{
          kind: "app",
          instance_id: "view-1",
          provider: "excalidraw",
          server: "excalidraw",
          tool: "create_view",
          resource_uri: "ui://excalidraw/mcp-app.html",
          status: "loading",
          input: { elements: "[]" },
          permissions: { clipboardWrite: true },
        }],
        citations: [],
        followups: [],
        error_code: null,
      }],
    } as unknown as ChatSessionDetail;

    expect(toUiMessages(detail)[0].blocks).toEqual([{
      kind: "app",
      instance_id: "view-1",
      provider: "excalidraw",
      server: "excalidraw",
      tool: "create_view",
      resource_uri: "ui://excalidraw/mcp-app.html",
      status: "loading",
      input: { elements: "[]" },
      permissions: { clipboardWrite: true },
      schema_version: 1,
      result: { content: [], structuredContent: {}, isError: false },
      csp: {},
      height: 525,
      public_fork: false,
    }]);
  });
});

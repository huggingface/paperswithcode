import { describe, expect, it } from "vitest";

import {
  isSponsoredChatModel,
  PRODUCTION_FALLBACK_CHAT_MODELS,
  providerForChatModel,
  toUiMessages,
  type ChatSessionDetail,
} from "@/lib/chatSessions";

describe("production model fallback", () => {
  it("offers Luna and the sponsored DeepSeek while GLM is hidden", () => {
    expect(PRODUCTION_FALLBACK_CHAT_MODELS).toEqual([
      {
        id: "gpt-5.6-luna@openai",
        label: "GPT-6 Luna",
        provider: "openai",
      },
      {
        id: "deepseek-ai/DeepSeek-V4.1-Flash-1017",
        label: "DeepSeek V4.1 Flash",
        provider: "huggingface",
        sponsored: true,
      },
    ]);
  });
});

describe("legacy model compatibility", () => {
  it("keeps the hidden historical Luna ID on OpenRouter", () => {
    expect(providerForChatModel([], "openai/gpt-5.6-luna")).toBe("openrouter");
  });

  it("recognizes production OpenAI Luna without discovery", () => {
    expect(providerForChatModel([], "gpt-5.6-luna@openai")).toBe("openai");
  });

  it("recognizes the sponsored model before discovery loads", () => {
    const sponsored = "deepseek-ai/DeepSeek-V4.1-Flash-1017";
    expect(isSponsoredChatModel([], sponsored)).toBe(true);
    expect(isSponsoredChatModel([], "moonshotai/Kimi-K3")).toBe(false);
    // Discovery wins once it has loaded.
    expect(isSponsoredChatModel(
      [{ id: sponsored, label: "DeepSeek", provider: "huggingface" }],
      sponsored,
    )).toBe(false);
  });
});

describe("toUiMessages", () => {
  it.each([
    ["hf_inference_billing_exhausted", /could not bill/],
    ["hf_inference_credential_expired", /Re-sign in with Hugging Face/],
    ["provider_rate_limit", /temporarily rate-limited/],
    ["provider_timeout", /timed out/],
    ["provider_unavailable", /provider failed/],
    ["openai_budget_exhausted", /direct OpenAI allowance is exhausted/],
    ["context_too_large", /too large/],
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

  it("restores a scope-blocked refusal stored only as content", () => {
    const detail: ChatSessionDetail = {
      id: "session-scope",
      title: "Test",
      selected_model: "gpt-5.6-luna@openai",
      created_at: "2026-10-11T00:00:00Z",
      updated_at: "2026-10-11T00:00:00Z",
      message_count: 2,
      is_busy: false,
      web_search_enabled: false,
      transcript_status: "ready",
      messages: [{
        id: "assistant-scope",
        turn_id: "turn-scope",
        sequence: 2,
        role: "assistant",
        content: "I can only help with AI research.",
        revision: 1,
        status: "complete",
        display_blocks: [],
        citations: [],
        followups: [],
        finish_reason: "scope_blocked",
        error_code: null,
      }],
    };

    expect(toUiMessages(detail)[0]).toMatchObject({
      blocks: [{ kind: "answer", text: "I can only help with AI research.", done: true }],
      finishReason: "scope_blocked",
    });
  });

  it("keeps a user stop as stopped-early after reload", () => {
    const detail: ChatSessionDetail = {
      id: "session-stopped",
      title: "Test",
      selected_model: "zai-org/GLM-5.2",
      created_at: "2026-07-31T00:00:00Z",
      updated_at: "2026-07-31T00:00:00Z",
      message_count: 1,
      is_busy: false,
      web_search_enabled: false,
      transcript_status: "ready",
      messages: [{
        id: "user-stopped",
        turn_id: "turn-stopped",
        sequence: 1,
        role: "user",
        content: "Question",
        revision: 1,
        status: "interrupted",
        display_blocks: [{ kind: "answer", text: "Partial", done: false }],
        citations: [],
        followups: [],
        error_code: "cancelled",
      }],
    };

    expect(toUiMessages(detail)[1]).toMatchObject({
      finishReason: "stopped",
      error: undefined,
      errorCode: undefined,
    });
  });

  it("surfaces worker-loss as a retryable failure instead of stopped-early", () => {
    const detail: ChatSessionDetail = {
      id: "session-worker-lost",
      title: "Test",
      selected_model: "zai-org/GLM-5.2",
      created_at: "2026-07-31T00:00:00Z",
      updated_at: "2026-07-31T00:00:00Z",
      message_count: 1,
      is_busy: false,
      web_search_enabled: false,
      transcript_status: "ready",
      messages: [{
        id: "user-worker-lost",
        turn_id: "turn-worker-lost",
        sequence: 1,
        role: "user",
        content: "Question",
        revision: 1,
        status: "interrupted",
        display_blocks: [{ kind: "answer", text: "Partial", done: false }],
        citations: [],
        followups: [],
        error_code: "external_worker_lost",
      }],
    };

    expect(toUiMessages(detail)[1].finishReason).toBeUndefined();
    expect(toUiMessages(detail)[1].error).toMatch(/lost contact/);
    expect(toUiMessages(detail)[1].errorCode).toBe("external_worker_lost");
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

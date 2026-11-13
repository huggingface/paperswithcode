import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CHAT_AUTO_SEND_KEY,
  CHAT_DRAFT_KEY,
  CHAT_MODEL_KEY,
} from "@/lib/chatLaunch";
import SharedChatView from "@/views/SharedChatView";

const shareId = "11111111-1111-4111-8111-111111111111";
const payload = {
  share_id: shareId,
  created_at: "2026-07-28T20:00:00Z",
  updated_at: "2026-07-28T20:00:00Z",
  model: "deepseek-ai/DeepSeek-V4-Flash-0731",
  model_label: "DeepSeek V4 Flash",
  model_provider: "huggingface",
  messages: [
    {
      id: "22222222-2222-4222-8222-222222222222",
      role: "user",
      content: "What is new?",
      display_blocks: [],
      citations: [],
      display_state: "complete",
      finish_reason: null,
      error: null,
    },
    {
      id: "33333333-3333-4333-8333-333333333333",
      role: "assistant",
      content: "See the paper.",
      display_blocks: [
        { kind: "reasoning", text: "Bounded reasoning" },
        {
          kind: "tool",
          schema_version: 2,
          id: "tool-1",
          name: "Bash",
          args: { command: "pwc paper search" },
          status: "success",
          took_ms: 5,
          content: [{ type: "text", text: "Bounded output", truncated: false }],
          metadata: { exit_code: 0, output_truncated: false },
        },
        {
          kind: "answer",
          text: "[See the paper](paper:2607.00001).",
          done: true,
          citations: [{
            position: 0,
            route_id: "2607.00001",
            title: "Shared citation",
            source_url: "https://arxiv.org/abs/2607.00001",
          }],
        },
      ],
      citations: [],
      display_state: "complete",
      finish_reason: null,
      error: null,
    },
  ],
};

function renderView() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/share/${shareId}`]}>
        <Routes>
          <Route path="/share/:shareId" element={<SharedChatView />} />
          <Route path="/chat" element={<div>Fresh private chat</div>} />
          <Route path="/:orgSlug" element={<div>Organization catch-all</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  sessionStorage.clear();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  ));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("SharedChatView", () => {
  it("loads anonymously and renders only the generic immutable transcript", async () => {
    renderView();

    expect(await screen.findByText("What is new?")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Shared conversation" })).toBeInTheDocument();
    expect(screen.queryByText("Organization catch-all")).not.toBeInTheDocument();
    expect(screen.queryByText("Private title")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit message" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Thought for/ })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("button", { name: /Bash/ })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("link", { name: "See the paper" })).toHaveAttribute(
      "href",
      "/paper/2607.00001",
    );
    expect(screen.getByText("Generated with DeepSeek V4 Flash")).toBeVisible();
    expect(screen.getByRole("link", { name: "Inference Providers" })).toHaveAttribute(
      "href",
      "https://huggingface.co/docs/inference-providers/en/index",
    );
    const attribution = screen.getByText("Generated with DeepSeek V4 Flash").parentElement;
    const fresh = screen.getByRole("heading", { name: "Start a new conversation" }).closest("section");
    expect(attribution?.nextElementSibling).toBe(fresh);
    const fetchInit = vi.mocked(fetch).mock.calls[0][1];
    expect(fetchInit).toHaveProperty("credentials", "omit");
    expect(document.title).toBe("Shared conversation");
    expect(document.head.querySelector('meta[name="robots"]')).toHaveAttribute(
      "content",
      "noindex,nofollow",
    );
  });

  it("truthfully attributes OpenRouter shared conversations", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ ...payload, model_provider: "openrouter" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    renderView();

    expect(await screen.findByText("Generated with DeepSeek V4 Flash")).toBeVisible();
    expect(screen.getByText(/Powered by/i)).toBeVisible();
    expect(screen.getByRole("link", { name: "OpenRouter" })).toHaveAttribute(
      "href", "https://openrouter.ai",
    );
  });

  it("shows no provider attribution for direct OpenAI conversations", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ ...payload, model_provider: "openai" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    renderView();

    expect(await screen.findByText("Generated with DeepSeek V4 Flash")).toBeVisible();
    expect(screen.queryByText(/Powered by/i)).not.toBeInTheDocument();
  });

  it("opens a public poster beside the transcript without loading private chat history", async () => {
    window.history.replaceState({}, "", `/share/${shareId}`);
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1280);
    const sharedPoster = {
      kind: "artifact",
      schema_version: 1,
      scope: "public",
      public_capability: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      identifier: "attention-poster",
      artifact_kind: "posterly",
      title: "Attention poster",
      status: "ready",
      version: 1,
      preview_mime: "image/png",
      source_language: "html",
      gate_status: "failed",
      total_bytes: 4096,
    };
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({
        ...payload,
        messages: payload.messages.map((message) => message.role === "assistant"
          ? { ...message, display_blocks: [...message.display_blocks, sharedPoster] }
          : message),
      }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    renderView();

    expect(await screen.findByRole("complementary", { name: "Attention poster" })).toBeVisible();
    expect(document.querySelector(".shared-chat-page"))
      .toHaveStyle({ height: "calc(100dvh - 60px)" });
    expect(screen.getByTestId("shared-conversation-pane").closest("[data-artifact-layout]"))
      .toHaveAttribute("data-artifact-layout", "split");
    expect(screen.getByAltText("Full preview of Attention poster")).toHaveAttribute(
      "src",
      expect.stringContaining(`/api/v1/chat/shares/${shareId}/artifacts/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/preview`),
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("/chat/sessions")))
      .toBe(false);
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("/chat/artifacts")))
      .toBe(false);
  });

  it("opens a fresh chat with the prompt as a draft so setup is shown before sending", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem(CHAT_MODEL_KEY, "stale-model");
    renderView();
    await screen.findByText("What is new?");

    await user.type(
      screen.getByPlaceholderText("Ask a new research question…"),
      "A completely new question",
    );
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByText("Fresh private chat")).toBeInTheDocument();
    expect(sessionStorage.getItem(CHAT_DRAFT_KEY)).toBe("A completely new question");
    expect(sessionStorage.getItem(CHAT_AUTO_SEND_KEY)).toBeNull();
    expect(sessionStorage.getItem(CHAT_MODEL_KEY)).toBeNull();
    expect(JSON.stringify({ ...sessionStorage })).not.toContain("What is new?");
  });

  it("explains staging access before continuing", async () => {
    vi.stubEnv("MODE", "staging");
    renderView();

    await screen.findByText("What is new?");
    expect(screen.getByText("Staging")).toBeVisible();
    expect(screen.getByText(/available only to approved Hugging Face users/)).toBeVisible();
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
  });

  it("renders the same non-enumerating not-found state for a missing capability", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(
      JSON.stringify({ detail: { code: "share_not_found", message: "Shared conversation not found" } }),
      { status: 404, headers: { "Content-Type": "application/json" } },
    ));
    renderView();

    expect(await screen.findByRole("heading", { name: "Shared conversation not found" })).toBeInTheDocument();
    expect(screen.getByText("This link is invalid or is no longer available.")).toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  });
});

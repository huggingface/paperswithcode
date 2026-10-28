import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CHAT_AUTO_SEND_KEY,
  CHAT_DRAFT_KEY,
  CHAT_MODEL_KEY,
  CHAT_REASONING_EFFORT_KEY,
  readQueuedChatLaunch,
} from "@/lib/chatLaunch";
import { chatApi } from "@/lib/api/chat";
import { papersApi } from "@/lib/api/papers";
import { DEFAULT_CHAT_MODEL, STAGING_FALLBACK_CHAT_MODELS } from "@/lib/chatSessions";
import { SUGGESTED_CHAT_PROMPTS } from "@/lib/chatPrompts";
import { AskAssistant } from "@/views/FeedView";

const auth = vi.hoisted(() => ({
  value: { user: { username: "owner" } as { username: string } | null, isLoading: false },
}));

vi.mock("@/lib/authContext", () => ({
  useAuth: () => auth.value,
  useOptionalAuth: () => auth.value,
}));

beforeEach(() => {
  auth.value = { user: { username: "owner" }, isLoading: false };
  vi.spyOn(chatApi, "getModels").mockResolvedValue({
    items: STAGING_FALLBACK_CHAT_MODELS,
    default_model: DEFAULT_CHAT_MODEL,
  });
  sessionStorage.clear();
  vi.stubEnv("MODE", "staging");
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

const renderAskAssistant = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<AskAssistant />} />
          <Route path="/chat/:sessionId" element={<div>Dedicated chat launched</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("AskAssistant", () => {
  it("shows the paper mention hint above the chat window", () => {
    renderAskAssistant();

    expect(screen.getByText(
      "Hint: type @ to bring papers into context, or press Tab to use a suggestion",
    )).toBeVisible();
  });

  it("fills the empty box with the shown suggestion on Tab", async () => {
    const user = userEvent.setup();
    renderAskAssistant();
    const textarea = screen.getByRole("textbox", { name: "Ask the assistant" });

    await user.click(textarea);
    await user.keyboard("{Tab}");

    expect(textarea).toHaveValue(SUGGESTED_CHAT_PROMPTS[0]);
    expect(textarea).toHaveFocus();
    await waitFor(() => expect(textarea).toHaveProperty(
      "selectionStart",
      SUGGESTED_CHAT_PROMPTS[0].length,
    ));
  });

  it("completes a started suggestion on Tab and previews the rest", async () => {
    const user = userEvent.setup();
    const { container } = renderAskAssistant();
    const textarea = screen.getByRole("textbox", { name: "Ask the assistant" });

    await user.type(textarea, "find rel");
    (textarea as HTMLTextAreaElement).setSelectionRange(2, 2);
    expect(container.querySelector(".chat-prompt-completion"))
      .toHaveTextContent("evant papers on RLVR");

    await user.keyboard("{Tab}");
    expect(textarea).toHaveValue("find relevant papers on RLVR");
    await waitFor(() => expect(textarea).toHaveProperty("selectionStart", 28));
    expect(container.querySelector(".chat-prompt-completion")).not.toBeInTheDocument();
  });

  it("leaves Tab to move focus when the text matches no suggestion", async () => {
    const user = userEvent.setup();
    renderAskAssistant();
    const textarea = screen.getByRole("textbox", { name: "Ask the assistant" });

    await user.type(textarea, "Compare diffusion models");
    await user.keyboard("{Tab}");

    expect(textarea).toHaveValue("Compare diffusion models");
    expect(textarea).not.toHaveFocus();
  });

  it("opens the canonical chat in a new tab on the Hugging Face Space mirror", async () => {
    vi.stubEnv("VITE_DISABLE_AUTH", "1");
    vi.stubEnv("VITE_CHAT_ENABLED", "0");
    const tab = { opener: window } as unknown as Window;
    const open = vi.spyOn(window, "open").mockReturnValue(tab);
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    renderAskAssistant();

    expect(screen.queryByText("Hint: type @ to bring papers into context")).not.toBeInTheDocument();
    const textarea = screen.getByRole("textbox", { name: "Ask the assistant" });
    fireEvent.change(textarea, { target: { value: "What is new in diffusion?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    const params = new URLSearchParams({ q: "What is new in diffusion?", model: DEFAULT_CHAT_MODEL });
    expect(open).toHaveBeenCalledWith(
      `https://paperswithcode.co/chat?${params}`,
      "_blank",
    );
    expect(tab.opener).toBeNull();
    expect(textarea).toHaveValue("");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("keeps the question as a link when the mirror's new tab is blocked", () => {
    vi.stubEnv("VITE_DISABLE_AUTH", "1");
    vi.stubEnv("VITE_CHAT_ENABLED", "0");
    vi.spyOn(window, "open").mockReturnValue(null);
    renderAskAssistant();

    const textarea = screen.getByRole("textbox", { name: "Ask the assistant" });
    fireEvent.change(textarea, { target: { value: "What is new in diffusion?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    const params = new URLSearchParams({ q: "What is new in diffusion?", model: DEFAULT_CHAT_MODEL });
    expect(textarea).toHaveValue("What is new in diffusion?");
    expect(screen.getByRole("link", { name: "Open this question on paperswithcode.co" }))
      .toHaveAttribute("href", `https://paperswithcode.co/chat?${params}`);
  });

  it("offers the four truthful staging model routes", () => {
    expect(STAGING_FALLBACK_CHAT_MODELS).toEqual([
      {
        id: "deepseek-ai/DeepSeek-V4-Flash-0731",
        label: "DeepSeek V4 Flash",
        provider: "huggingface",
      },
      {
        id: "moonshotai/Kimi-K3",
        label: "Kimi K3",
        provider: "huggingface",
      },
      {
        id: "gpt-5.6-luna@openrouter",
        label: "GPT-5.6 Luna",
        provider: "openrouter",
      },
      {
        id: "gpt-5.6-luna@openai",
        label: "GPT-6 Luna (Direct)",
        provider: "openai",
      },
    ]);
    renderAskAssistant();

    const picker = screen.getByLabelText("Research model");
    expect(picker).toHaveValue("gpt-5.6-luna@openai");
    expect([...picker.querySelectorAll("optgroup")].map((group) => group.label)).toEqual([
      "Hugging Face Inference Providers",
      "OpenRouter",
      "OpenAI",
    ]);
    expect([...picker.querySelectorAll("option")].map((option) => option.value)).toEqual([
      "deepseek-ai/DeepSeek-V4-Flash-0731",
      "moonshotai/Kimi-K3",
      "gpt-5.6-luna@openrouter",
      "gpt-5.6-luna@openai",
    ]);
    expect(screen.queryByText(/^Via\b/)).not.toBeInTheDocument();

    fireEvent.change(picker, { target: { value: "deepseek-ai/DeepSeek-V4-Flash-0731" } });
    expect(screen.queryByText(/^Via\b/)).not.toBeInTheDocument();
  });

  it("offers Luna and the free DeepSeek to signed-out production visitors", () => {
    vi.stubEnv("MODE", "production");
    auth.value = { user: null, isLoading: false };
    renderAskAssistant();

    const picker = screen.getByRole("combobox", { name: "Research model" });
    expect(picker).toHaveValue("gpt-5.6-luna@openai");
    expect([...picker.querySelectorAll("option")].map((option) => option.textContent)).toEqual([
      "DeepSeek V4.1 Flash",
      "GPT-6 Luna",
    ]);
    expect(chatApi.getModels).not.toHaveBeenCalled();
  });

  it("offers the discovered production models to signed-in users", async () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_CHAT_ENABLED", "1");
    vi.mocked(chatApi.getModels).mockResolvedValue({
      items: [{ id: "gpt-5.6-luna@openai", label: "GPT-6 Luna", provider: "openai" }],
      default_model: "gpt-5.6-luna@openai",
    });
    renderAskAssistant();

    await waitFor(() => expect(screen.queryByRole("combobox", { name: "Research model" }))
      .not.toBeInTheDocument());
    expect(screen.getByLabelText("Research model")).toHaveTextContent("GPT-6 Luna");
  });

  it("types, holds, erases, and rotates the suggested placeholder", () => {
    vi.useFakeTimers();
    renderAskAssistant();
    const textarea = screen.getByRole("textbox", { name: "Ask the assistant" });
    const firstPrompt = SUGGESTED_CHAT_PROMPTS[0];

    expect(textarea).toHaveAttribute("placeholder", firstPrompt.slice(0, 1));

    act(() => vi.advanceTimersByTime(45 * (firstPrompt.length - 1)));
    expect(textarea).toHaveAttribute("placeholder", firstPrompt);

    act(() => vi.advanceTimersByTime(1_800));
    expect(textarea).toHaveAttribute("placeholder", firstPrompt.slice(0, -1));

    act(() => vi.advanceTimersByTime(25 * (firstPrompt.length - 1) + 350));
    expect(textarea).toHaveAttribute("placeholder", SUGGESTED_CHAT_PROMPTS[1].slice(0, 1));
  });

  it("reserves enough height for wrapped suggested prompts", () => {
    const scrollHeight = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "scrollHeight",
    );
    Object.defineProperty(HTMLTextAreaElement.prototype, "scrollHeight", {
      configurable: true,
      get(this: HTMLTextAreaElement) {
        return this.placeholder.length;
      },
    });

    try {
      renderAskAssistant();

      const textarea = screen.getByRole("textbox", { name: "Ask the assistant" });
      expect(textarea).toHaveStyle({
        height: `${Math.max(...SUGGESTED_CHAT_PROMPTS.map((prompt) => prompt.length))}px`,
      });
      expect(textarea).toHaveAttribute("placeholder", SUGGESTED_CHAT_PROMPTS[0].slice(0, 1));
    } finally {
      if (scrollHeight) {
        Object.defineProperty(HTMLTextAreaElement.prototype, "scrollHeight", scrollHeight);
      } else {
        delete (HTMLTextAreaElement.prototype as { scrollHeight?: number }).scrollHeight;
      }
    }
  });

  it("launches chat with the typed question", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({
      id: "11111111-1111-4111-8111-111111111111",
      title: "New chat",
      selected_model: DEFAULT_CHAT_MODEL,
      created_at: "2026-08-03T00:00:00Z",
      updated_at: "2026-08-03T00:00:00Z",
      message_count: 0,
      is_busy: false,
    }), { status: 201, headers: { "Content-Type": "application/json" } }));
    const user = userEvent.setup();
    renderAskAssistant();
    const question = "Compare recent vision-language models";

    await user.type(screen.getByRole("textbox", { name: "Ask the assistant" }), question);
    await user.click(screen.getByRole("button", { name: "Ask the assistant" }));

    expect(await screen.findByText("Dedicated chat launched")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/chat/sessions"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          selected_model: DEFAULT_CHAT_MODEL,
          reasoning_effort: "medium",
        }),
      }),
    );
    expect(sessionStorage.getItem(CHAT_DRAFT_KEY)).toBe(question);
    expect(sessionStorage.getItem(CHAT_MODEL_KEY)).toBe(DEFAULT_CHAT_MODEL);
    expect(sessionStorage.getItem(CHAT_AUTO_SEND_KEY)).toBe("1");
    expect(sessionStorage.getItem(CHAT_REASONING_EFFORT_KEY)).toBe("medium");
  });

  it("does not offer a reasoning effort picker", () => {
    renderAskAssistant();

    expect(screen.queryByRole("button", { name: /Reasoning effort/ })).not.toBeInTheDocument();
  });

  it("selects an inline paper and carries its structured mention into chat", async () => {
    vi.stubEnv("VITE_CHAT_ENABLED", "1");
    vi.spyOn(chatApi, "getAvailability").mockResolvedValue({
      status: "available",
      reason: null,
      expected_recovery_at: null,
      paper_mentions_enabled: true,
      web_search_available: false,
    });
    vi.spyOn(papersApi, "search").mockResolvedValue({
      next_page: null,
      previous_page: null,
      results: [{
        id: "42",
        arxiv_id: "2501.00001",
        source: "arxiv",
        source_url: null,
        url_abs: "https://arxiv.org/abs/2501.00001",
        url_pdf: null,
        title: "Deep Paper",
        abstract: "",
        authors: [],
        published: "2026-01-01",
        version: "v1",
        is_latest_version: true,
        citation_count: 0,
      }],
    });
    vi.spyOn(chatApi, "prewarmPaperContext").mockResolvedValue(undefined);
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({
      id: "11111111-1111-4111-8111-111111111111",
      title: "New chat",
      selected_model: DEFAULT_CHAT_MODEL,
      created_at: "2026-08-03T00:00:00Z",
      updated_at: "2026-08-03T00:00:00Z",
      message_count: 0,
      is_busy: false,
    }), { status: 201, headers: { "Content-Type": "application/json" } }));
    renderAskAssistant();
    const textarea = screen.getByRole("combobox", { name: "Ask the assistant" });

    fireEvent.change(textarea, { target: { value: "Compare @deep", selectionStart: 13 } });
    expect(await screen.findByRole("option", { name: /Deep Paper/ })).toBeInTheDocument();
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(textarea).toHaveValue("Compare Deep Paper ");
    expect(chatApi.prewarmPaperContext).toHaveBeenCalledWith("2501.00001");
    fireEvent.click(screen.getByRole("button", { name: "Ask the assistant" }));

    expect(await screen.findByText("Dedicated chat launched")).toBeInTheDocument();
    expect(JSON.parse(sessionStorage.getItem(CHAT_DRAFT_KEY) ?? "null")).toEqual({
      text: "Compare Deep Paper",
      paperMentions: [expect.objectContaining({
        route_id: "2501.00001",
        title: "Deep Paper",
        start: 8,
        end: 18,
      })],
    });
    expect(readQueuedChatLaunch()?.draft).toEqual({
      text: "Compare Deep Paper",
      paperMentions: [expect.objectContaining({ route_id: "2501.00001", start: 8, end: 18 })],
    });
  });

  it("launches a new chat from the homepage composer", async () => {
    vi.stubEnv("VITE_CHAT_ENABLED", "1");
    vi.spyOn(chatApi, "getAvailability").mockResolvedValue({
      status: "available",
      reason: null,
      expected_recovery_at: null,
      paper_mentions_enabled: true,
      web_search_available: true,
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({
      id: "11111111-1111-4111-8111-111111111111",
      title: "New chat",
      selected_model: DEFAULT_CHAT_MODEL,
      created_at: "2026-08-03T00:00:00Z",
      updated_at: "2026-08-03T00:00:00Z",
      message_count: 0,
      is_busy: false,
      web_search_enabled: false,
    }), { status: 201, headers: { "Content-Type": "application/json" } }));
    const user = userEvent.setup();
    renderAskAssistant();

    expect(await screen.findByLabelText("Research model"))
      .toHaveValue("gpt-5.6-luna@openai");
    expect(screen.queryByRole("switch", { name: "Web search" })).not.toBeInTheDocument();
    await user.type(
      screen.getByRole("combobox", { name: "Ask the assistant" }),
      "Find the latest vision-language model release",
    );
    await user.click(screen.getByRole("button", { name: "Ask the assistant" }));

    expect(await screen.findByText("Dedicated chat launched")).toBeInTheDocument();
  });
});

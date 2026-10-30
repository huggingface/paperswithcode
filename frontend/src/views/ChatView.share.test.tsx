import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { chatApi } from "@/lib/api/chat";
import type { ChatMessage } from "@/lib/chat";
import {
  CHAT_AUTO_SEND_KEY,
  CHAT_DRAFT_KEY,
  CHAT_MODEL_KEY,
} from "@/lib/chatLaunch";

const mocks = vi.hoisted(() => ({
  busy: false,
  activeSessionId: null as string | null,
  authLoading: false,
  authUser: { username: "owner", hf_subject: "hf-owner" },
  messages: [{
    id: "user-1",
    role: "user" as const,
    text: "Question",
    revision: 1,
    status: "complete",
  }],
  load: vi.fn(),
  reset: vi.fn(),
  send: vi.fn(() => true),
  stop: vi.fn(),
  toggleBlock: vi.fn(),
  editAndResend: vi.fn(() => true),
  getSession: vi.fn(),
  listSessions: vi.fn(),
  getChatModels: vi.fn(),
  createShare: vi.fn(),
  toast: vi.fn(),
  clipboardWrite: vi.fn(),
  hfLoginUrl: vi.fn(() => window.location.href),
  chatOptions: null as {
    sessionId: string | null;
    webSearchEnabled: boolean;
    onSessionId: (id: string, origin: string | null) => void;
    onTitle: (title: string, id: string | null) => void;
    onSettled: (id: string | null) => void;
  } | null,
}));

vi.mock("@/hooks/useChat", () => ({
  useChat: (options: NonNullable<typeof mocks.chatOptions>) => {
    mocks.chatOptions = options;
    return {
      busy: mocks.busy,
      activeSessionId: mocks.activeSessionId,
      selectedBusy: mocks.busy && mocks.activeSessionId === options.sessionId,
      messages: mocks.messages,
      papers: {},
      sessionError: "",
      load: mocks.load,
      reset: mocks.reset,
      send: mocks.send,
      stop: mocks.stop,
      toggleBlock: mocks.toggleBlock,
      editAndResend: mocks.editAndResend,
    };
  },
}));
vi.mock("@/lib/authContext", () => ({
  useAuth: () => ({
    user: mocks.authUser,
    isLoading: mocks.authLoading,
  }),
}));
vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: mocks.toast }),
}));
vi.mock("@/lib/apiUrl", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/apiUrl")>(),
  hfLoginUrl: mocks.hfLoginUrl,
}));
vi.mock("@/lib/chatSessions", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/chatSessions")>();
  return {
    ...original,
    listSessions: mocks.listSessions,
    toUiMessages: () => mocks.messages,
  };
});

import ChatView from "@/views/ChatView";

const sessionId = "11111111-1111-4111-8111-111111111111";
const session = {
  id: sessionId,
  title: "Private title",
  selected_model: "google/gemma-4-31B-it",
  created_at: "2026-07-28T20:00:00Z",
  updated_at: "2026-07-28T20:00:00Z",
  message_count: 1,
  is_busy: false,
  web_search_enabled: false,
};

let queryClient: QueryClient;

const LocationProbe = () => {
  const location = useLocation();
  return <output data-testid="chat-location">{location.pathname}</output>;
};

function chatElement(path = `/chat/${sessionId}`) {
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/chat/:sessionId?"
            element={<><ChatView /><LocationProbe /></>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderChat(path = `/chat/${sessionId}`) {
  return render(chatElement(path));
}

beforeEach(() => {
  vi.restoreAllMocks();
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  localStorage.clear();
  sessionStorage.clear();
  vi.unstubAllEnvs();
  vi.spyOn(chatApi, "getSession").mockImplementation((id) => mocks.getSession(id));
  vi.spyOn(chatApi, "getModels").mockImplementation(() => mocks.getChatModels());
  vi.spyOn(chatApi, "createOrRefreshShare").mockImplementation((id) => mocks.createShare(id));
  vi.spyOn(chatApi, "getOpenAIUsage").mockResolvedValue({ used_percent: 0, remaining_percent: 100, resets_at: "2026-11-01T00:00:00Z", available: true, as_of: "2026-10-03T00:00:00Z" });
  mocks.busy = false;
  mocks.activeSessionId = null;
  mocks.authLoading = false;
  mocks.messages.splice(0, mocks.messages.length, {
    id: "user-1",
    role: "user",
    text: "Question",
    revision: 1,
    status: "complete",
  });
  mocks.chatOptions = null;
  mocks.send.mockReset().mockReturnValue(true);
  mocks.hfLoginUrl.mockReset().mockImplementation(() => window.location.href);
  mocks.load.mockReset();
  mocks.getSession.mockReset().mockResolvedValue({
    ...session,
    transcript_status: "ready",
    messages: [],
  });
  mocks.listSessions.mockReset().mockResolvedValue([session]);
  mocks.getChatModels.mockReset().mockResolvedValue({
    items: [{ id: session.selected_model, label: "Default" }],
    default_model: session.selected_model,
  });
  mocks.createShare.mockReset().mockResolvedValue({
    share_id: "22222222-2222-4222-8222-222222222222",
    public_path: "/share/22222222-2222-4222-8222-222222222222",
    created_at: "2026-07-28T20:00:00Z",
    updated_at: "2026-07-28T20:00:00Z",
  });
  mocks.toast.mockReset();
  mocks.clipboardWrite.mockReset().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: mocks.clipboardWrite },
  });
});

describe("ChatView sidebar navigation", () => {
  it.each([390, 900, 1200])("reveals a new chat at viewport width %i", async (width) => {
    vi.spyOn(window, "innerWidth", "get").mockReturnValue(width);
    const user = userEvent.setup();
    renderChat();
    await screen.findByText(session.title, { selector: ".chat-session-title" });
    if (width <= 900) await user.click(screen.getByTitle("Open sidebar"));

    await user.click(screen.getByRole("button", { name: "New chat" }));

    expect(screen.getByTestId("chat-location").textContent).toBe("/chat");
    expect(document.querySelector(".chat-sidebar")?.classList.contains("chat-sidebar-closed"))
      .toBe(width <= 900);
  });

  it.each([
    [390, "/chat"],
    [900, "/chat"],
    [1200, "/chat"],
    [390, `/chat/${sessionId}`],
  ])("reveals a selected chat at viewport width %i from %s", async (width, path) => {
    vi.spyOn(window, "innerWidth", "get").mockReturnValue(width);
    const user = userEvent.setup();
    renderChat(path);
    const title = await screen.findByText(session.title, { selector: ".chat-session-title" });
    if (width <= 900) await user.click(screen.getByTitle("Open sidebar"));

    await user.click(title);

    expect(screen.getByTestId("chat-location").textContent).toBe(`/chat/${sessionId}`);
    expect(document.querySelector(".chat-sidebar")?.classList.contains("chat-sidebar-closed"))
      .toBe(width <= 900);
  });
});

describe("ChatView inference authorization", () => {
  it("renders authenticated previous-chat navigation, conversation, and poster as three columns", async () => {
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1400);
    (mocks.messages as unknown as ChatMessage[]).splice(0, mocks.messages.length,
      { id: "user-1", role: "user", text: "Create a poster", revision: 1, status: "complete" },
      {
        id: "assistant-1",
        role: "assistant",
        blocks: [{
          kind: "artifact",
          schema_version: 1,
          scope: "owner",
          publication_id: "poster-1",
          artifact_id: "artifact-1",
          version_id: "version-1",
          identifier: "attention-poster",
          artifact_kind: "posterly",
          title: "Attention poster",
          status: "ready",
          version: 1,
          preview_mime: "image/png",
          source_language: "html",
          gate_status: "passed",
          total_bytes: 4096,
        }],
      },
    );
    renderChat();

    const card = await screen.findByRole("button", { name: /Attention poster/u });
    await userEvent.click(card);
    expect(screen.getByRole("navigation", { name: "Chat history" })).toBeVisible();
    expect(screen.getByTestId("active-chat-pane")).toBeVisible();
    expect(await screen.findByRole("complementary", { name: "Attention poster" })).toBeVisible();
    expect(screen.getByTestId("active-chat-pane").closest("[data-artifact-layout]"))
      .toHaveAttribute("data-artifact-layout", "split");
  });

  it("keeps the composer disabled until authentication finishes loading", async () => {
    mocks.messages.length = 0;
    mocks.authLoading = true;
    renderChat("/chat");

    const input = screen.getByPlaceholderText("Ask anything about research…");
    await userEvent.type(input, "A fast prompt");

    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    expect(mocks.send).not.toHaveBeenCalled();
    expect(mocks.hfLoginUrl).not.toHaveBeenCalled();
  });

  it("returns inference authorization to the reserved homepage session", async () => {
    mocks.messages.length = 0;
    sessionStorage.setItem(CHAT_DRAFT_KEY, "Compare recent vision-language models");
    sessionStorage.setItem(CHAT_MODEL_KEY, session.selected_model);
    sessionStorage.setItem(CHAT_AUTO_SEND_KEY, "1");
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({
      connected: false,
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));

    renderChat();

    await waitFor(() => expect(mocks.hfLoginUrl).toHaveBeenCalledWith(
      `/chat/${sessionId}`,
      { authorizeInference: true },
    ));
  });

  it("loads a reserved chat before auto-sending its queued home-page prompt", async () => {
    mocks.messages.length = 0;
    let resolveSession!: (value: typeof session & { transcript_status: string; messages: never[] }) => void;
    let resolveBilling!: (value: Response) => void;
    mocks.getSession.mockReturnValueOnce(new Promise((resolve) => {
      resolveSession = resolve;
    }));
    sessionStorage.setItem("pwc:chat-oauth-draft", "Compare recent vision-language models");
    sessionStorage.setItem("pwc:chat-oauth-model", session.selected_model);
    sessionStorage.setItem("pwc:chat-oauth-auto-send", "1");
    vi.spyOn(globalThis, "fetch").mockReturnValueOnce(new Promise((resolve) => {
      resolveBilling = resolve;
    }));

    renderChat();

    await waitFor(() => expect(mocks.getSession).toHaveBeenCalledWith(sessionId));
    expect(await screen.findByText("Compare recent vision-language models")).toBeVisible();
    expect(screen.queryByText("Ask Papers With Code")).not.toBeInTheDocument();
    expect(mocks.send).not.toHaveBeenCalled();

    resolveSession({ ...session, transcript_status: "ready", messages: [] });

    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/me/inference-billing"),
      expect.anything(),
    ));

    resolveBilling(new Response(JSON.stringify({ connected: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));

    await waitFor(() => expect(mocks.send).toHaveBeenCalledWith(
      { text: "Compare recent vision-language models", paperMentions: [] },
    ));
  });

  it("starts inference authorization on the first chat when permission is missing", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      new Response(JSON.stringify({
        connected: false,
        available: true,
        remaining_percent: 100,
        used_percent: 0,
        resets_at: "2026-09-01T00:00:00Z",
        as_of: "2026-08-14T00:00:00Z",
        ...(String(input).includes("/me/inference-billing")
          ? { connected: false }
          : {}),
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const user = userEvent.setup();
    renderChat("/chat");

    const composer = await screen.findByRole("combobox");
    await user.type(composer, "What is new in vision-language models?");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(mocks.hfLoginUrl).toHaveBeenCalledWith("/chat", { authorizeInference: true }));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/me/inference-billing"),
      expect.objectContaining({ credentials: "include" }),
    );
    expect(JSON.parse(sessionStorage.getItem("pwc:chat-oauth-draft") ?? "null")).toEqual({
      text: "What is new in vision-language models?",
      paperMentions: [],
    });
    expect(sessionStorage.getItem("pwc:chat-oauth-auto-send")).toBe("1");
    expect(mocks.send).not.toHaveBeenCalled();
  });

  it("sends the sponsored model without asking for inference permission", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    mocks.getChatModels.mockResolvedValue({
      items: [{
        id: "deepseek-ai/DeepSeek-V4.1-Flash-1017",
        label: "DeepSeek V4.1 Flash",
        provider: "huggingface",
        sponsored: true,
      }],
      default_model: "deepseek-ai/DeepSeek-V4.1-Flash-1017",
    });
    const user = userEvent.setup();
    renderChat("/chat");

    const composer = await screen.findByRole("combobox");
    await user.type(composer, "What is new in vision-language models?");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(mocks.send).toHaveBeenCalled());
    expect(mocks.hfLoginUrl).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/me/inference-billing"),
      expect.anything(),
    );
  });

  it("sends directly when inference permission is already connected", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      new Response(JSON.stringify({
        connected: String(input).includes("/me/inference-billing"),
        available: true,
        remaining_percent: 100,
        used_percent: 0,
        resets_at: "2026-09-01T00:00:00Z",
        as_of: "2026-08-14T00:00:00Z",
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const user = userEvent.setup();
    renderChat("/chat");

    const composer = await screen.findByRole("combobox");
    await user.type(composer, "Explain this benchmark");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(mocks.send).toHaveBeenCalledWith({
      text: "Explain this benchmark",
      paperMentions: [],
    }));
    expect(mocks.hfLoginUrl).not.toHaveBeenCalled();
    expect(screen.queryByText(/% left this month/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/connected OpenRouter key will be used/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Powered by OpenRouter/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "OpenRouter" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/chat/usage"))).toBe(false);
  });

  it("auto-sends an authorized prompt exactly once across remounts", async () => {
    sessionStorage.setItem("pwc:chat-oauth-draft", "Exactly once prompt");
    sessionStorage.setItem("pwc:chat-oauth-model", session.selected_model);
    sessionStorage.setItem("pwc:chat-oauth-auto-send", "1");
    sessionStorage.setItem("pwc:chat-oauth-attempted", "1");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ connected: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const first = renderChat("/chat");
    await waitFor(() => expect(mocks.send).toHaveBeenCalledWith({
      text: "Exactly once prompt",
      paperMentions: [],
    }));
    expect(mocks.send).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem("pwc:chat-oauth-auto-send")).toBeNull();
    expect(sessionStorage.getItem("pwc:chat-oauth-attempted")).toBeNull();

    first.unmount();
    renderChat("/chat");
    await waitFor(() => expect(mocks.listSessions).toHaveBeenCalled());
    expect(mocks.send).toHaveBeenCalledTimes(1);
  });

  it("restores the prompt instead of looping after authorization cancellation", async () => {
    sessionStorage.setItem("pwc:chat-oauth-draft", "Restore this prompt");
    sessionStorage.setItem("pwc:chat-oauth-model", session.selected_model);
    sessionStorage.setItem("pwc:chat-oauth-auto-send", "1");
    sessionStorage.setItem("pwc:chat-oauth-attempted", "1");
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ connected: false }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    renderChat("/chat");

    const composer = await screen.findByRole("combobox");
    await waitFor(() => expect(composer).toHaveValue("Restore this prompt"));
    expect(screen.getByText(/authorization was not completed/i)).toBeVisible();
    expect(mocks.hfLoginUrl).not.toHaveBeenCalled();
    expect(mocks.send).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("pwc:chat-oauth-auto-send")).toBeNull();
    expect(sessionStorage.getItem("pwc:chat-oauth-attempted")).toBeNull();
  });
});

describe("ChatView billing notice", () => {
  it("can be dismissed permanently in this browser", async () => {
    vi.stubEnv("VITE_CHAT_LIVE", "1");
    const user = userEvent.setup();
    const rendered = renderChat();

    const dismiss = await screen.findByRole("button", {
      name: "Dismiss billing notice",
    });
    expect(screen.getByRole("link", { name: "Review usage" })).toBeVisible();

    await user.click(dismiss);

    expect(screen.queryByRole("link", { name: "Review usage" })).not.toBeInTheDocument();
    expect(localStorage.getItem("pwc.chat.billing-notice-dismissed.v1")).toBe("1");

    rendered.unmount();
    renderChat();
    await waitFor(() => expect(mocks.listSessions).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: "Review usage" })).not.toBeInTheDocument();
  });
});

describe("ChatView sharing", () => {
  it("is absent before a persisted non-empty session exists", async () => {
    renderChat("/chat");
    await waitFor(() => expect(mocks.listSessions).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Share conversation" })).not.toBeInTheDocument();
  });

  it("publishes, copies a current-origin URL, and shows the exact success toast", async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: mocks.clipboardWrite },
    });
    renderChat();
    const button = await screen.findByRole("button", { name: "Share conversation" });

    await user.click(button);

    expect(mocks.createShare).toHaveBeenCalledWith(sessionId);
    expect(mocks.clipboardWrite).toHaveBeenCalledWith(
      `${window.location.origin}/share/22222222-2222-4222-8222-222222222222`,
    );
    expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({
      title: "Public link copied to your clipboard",
      description: "Anyone with this link can see this conversation.",
    }));
    expect(button).toHaveTextContent("Share");
  });

  it("keeps the share and opens one manual-copy fallback on clipboard rejection", async () => {
    const user = userEvent.setup();
    mocks.clipboardWrite.mockRejectedValueOnce(new Error("denied"));
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: mocks.clipboardWrite },
    });
    renderChat();

    await user.click(await screen.findByRole("button", { name: "Share conversation" }));

    expect(await screen.findByRole("dialog", { name: "Public link created" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Public conversation link" })).toHaveValue(
      `${window.location.origin}/share/22222222-2222-4222-8222-222222222222`,
    );
    expect(screen.getByText(/Anyone with this link can see this conversation/)).toBeVisible();
    expect(mocks.createShare).toHaveBeenCalledTimes(1);
    expect(mocks.toast).not.toHaveBeenCalledWith(expect.objectContaining({
      title: "Public link copied to your clipboard",
    }));
  });

  it("disables sharing while generation is active", async () => {
    const rendered = renderChat();
    expect(await screen.findByRole("button", { name: "Share conversation" })).toBeEnabled();
    mocks.busy = true;
    mocks.activeSessionId = sessionId;
    rendered.rerender(chatElement());
    expect(screen.getByRole("button", { name: "Share conversation" })).toBeDisabled();
  });

  it("disables sharing while its publication request is pending", async () => {
    const user = userEvent.setup();
    let resolveShare!: (value: {
      share_id: string;
      public_path: string;
      created_at: string;
      updated_at: string;
    }) => void;
    mocks.createShare.mockReturnValueOnce(new Promise((resolve) => {
      resolveShare = resolve;
    }));
    renderChat();

    const button = await screen.findByRole("button", { name: "Share conversation" });
    await user.click(button);

    expect(button).toBeDisabled();
    resolveShare({
      share_id: "22222222-2222-4222-8222-222222222222",
      public_path: "/share/22222222-2222-4222-8222-222222222222",
      created_at: "2026-07-28T20:00:00Z",
      updated_at: "2026-07-28T20:00:00Z",
    });
    await waitFor(() => expect(button).toBeEnabled());
  });

  it("does not claim copy success when publication fails", async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: mocks.clipboardWrite },
    });
    mocks.createShare.mockRejectedValueOnce(new Error("Not allowed"));
    renderChat();
    await user.click(await screen.findByRole("button", { name: "Share conversation" }));

    expect(mocks.clipboardWrite).not.toHaveBeenCalled();
    expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({
      variant: "destructive",
      title: "Share failed",
    }));
    expect(mocks.toast).not.toHaveBeenCalledWith(expect.objectContaining({
      title: "Public link copied to your clipboard",
    }));
  });
});

describe("ChatView focus refresh", () => {
  it("refreshes the sidebar without reloading and aborting the active transcript", async () => {
    renderChat();
    await waitFor(() => expect(mocks.load).toHaveBeenCalledTimes(1));
    mocks.getSession.mockClear();
    mocks.load.mockClear();
    mocks.listSessions.mockClear();

    window.dispatchEvent(new Event("focus"));

    await waitFor(() => expect(mocks.listSessions).toHaveBeenCalledTimes(1));
    expect(mocks.getSession).not.toHaveBeenCalled();
    expect(mocks.load).not.toHaveBeenCalled();
  });
});

describe("ChatView navigation", () => {
  it("loads an earlier conversation while another response is generating", async () => {
    const earlierSession = {
      ...session,
      id: "33333333-3333-4333-8333-333333333333",
      title: "Earlier chat",
      updated_at: "2026-07-27T20:00:00Z",
    };
    mocks.busy = true;
    mocks.listSessions.mockResolvedValue([session, earlierSession]);
    mocks.getSession.mockImplementation(async (id: string) => ({
      ...(id === earlierSession.id ? earlierSession : session),
      transcript_status: "ready",
      messages: [],
    }));
    const user = userEvent.setup();
    renderChat();
    await waitFor(() => expect(mocks.load).toHaveBeenCalledTimes(1));
    mocks.load.mockClear();

    await user.click(await screen.findByText("Earlier chat", { selector: ".chat-session-title" }));

    await waitFor(() => expect(mocks.getSession).toHaveBeenCalledWith(earlierSession.id));
    await waitFor(() => expect(mocks.load).toHaveBeenCalledWith(
      mocks.messages,
      earlierSession.id,
      false,
      { model: earlierSession.selected_model, webSearchEnabled: false, reasoningEffort: "high" },
    ));
    expect(screen.queryByText("Loading conversation…")).not.toBeInTheDocument();
  });
});

describe("ChatView new-session sidebar", () => {
  it("replaces the new-chat URL with the admitted session ID", async () => {
    mocks.listSessions.mockResolvedValue([]);
    renderChat("/chat");
    await waitFor(() => expect(mocks.listSessions).toHaveBeenCalled());

    act(() => mocks.chatOptions?.onSessionId(sessionId, null));

    expect(await screen.findByTestId("chat-location")).toHaveTextContent(
      `/chat/${sessionId}`,
    );
  });

  it("inserts the session at stream start and applies streamed title deltas", async () => {
    mocks.listSessions.mockResolvedValue([]);
    renderChat("/chat");
    await waitFor(() => expect(mocks.listSessions).toHaveBeenCalled());

    act(() => mocks.chatOptions?.onSessionId(sessionId, null));
    expect(await screen.findByText("New chat", { selector: ".chat-session-title" })).toBeInTheDocument();

    act(() => mocks.chatOptions?.onTitle("Good OCR Models", sessionId));
    expect(await screen.findByText("Good OCR Models", { selector: ".chat-session-title" })).toBeInTheDocument();
  });

  it("does not reset a busy new-session stream while its route catches up", async () => {
    mocks.messages.length = 0;
    mocks.busy = true;
    mocks.listSessions.mockResolvedValue([]);
    renderChat("/chat");
    await waitFor(() => expect(mocks.listSessions).toHaveBeenCalled());

    act(() => mocks.chatOptions?.onSessionId(sessionId, null));

    expect(await screen.findByTestId("chat-location")).toHaveTextContent(
      `/chat/${sessionId}`,
    );
    expect(mocks.reset).not.toHaveBeenCalled();
  });
});

describe("ChatView web search", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_CHAT_LIVE", "1");
    vi.spyOn(chatApi, "getAvailability").mockResolvedValue({
      status: "available",
      reason: null,
      expected_recovery_at: null,
      paper_mentions_enabled: true,
      web_search_available: true,
    });
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => (
      new Response(JSON.stringify({ connected: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    ));
  });

  it("offers no web search switch on a new chat", async () => {
    renderChat("/chat");

    await screen.findByRole("combobox");
    expect(screen.queryByRole("switch", { name: "Web search" })).not.toBeInTheDocument();
    await waitFor(() => expect(mocks.chatOptions?.webSearchEnabled).toBe(true));
  });

  it("enables web search for a session saved with it off", async () => {
    mocks.getSession.mockResolvedValueOnce({
      ...session,
      web_search_enabled: false,
      transcript_status: "ready",
      messages: [],
    });

    renderChat();

    await waitFor(() => expect(mocks.getSession).toHaveBeenCalled());
    await waitFor(() => expect(mocks.chatOptions?.webSearchEnabled).toBe(true));
  });

  it("enables web search for a queued homepage launch", async () => {
    sessionStorage.setItem(CHAT_DRAFT_KEY, "Find recent multimodal model releases");
    sessionStorage.setItem(CHAT_MODEL_KEY, session.selected_model);
    sessionStorage.setItem(CHAT_AUTO_SEND_KEY, "1");
    mocks.getSession.mockResolvedValueOnce({
      ...session,
      transcript_status: "ready",
      messages: [],
    });

    renderChat();

    await waitFor(() => expect(mocks.send).toHaveBeenCalled());
    expect(mocks.chatOptions?.webSearchEnabled).toBe(true);
  });
});

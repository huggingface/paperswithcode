import type { ComponentProps, ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatEvent } from "@/lib/chat";
import type { ChatSessionDetail } from "@/lib/chatSessions";
import type { ChatComposerSurface } from "@/components/chat/ChatComposerSurface";
import type { ChatConversation } from "@/components/chat/ChatConversation";

const mocks = vi.hoisted(() => ({
  stream: vi.fn(), resume: vi.fn(), getSession: vi.fn(), listSessions: vi.fn(),
  user: { hf_subject: "owner", username: "owner" } as { hf_subject: string; username: string } | null,
  authLoading: false,
  frames: [] as Array<{ path: string; text: string }>,
}));
vi.mock("@/lib/authContext", () => ({ useAuth: () => ({ user: mocks.user, isLoading: mocks.authLoading }) }));
vi.mock("@/lib/chat", async (original) => ({
  ...await original<typeof import("@/lib/chat")>(),
  streamChat: mocks.stream, resumeChat: mocks.resume, isChatLive: () => false,
}));
vi.mock("@/lib/chatSessions", async (original) => ({
  ...await original<typeof import("@/lib/chatSessions")>(),
  listSessions: mocks.listSessions,
}));
vi.mock("@/components/chat/ChatComposerSurface", () => ({
  ChatComposerSurface: ({ composerProps: props }: ComponentProps<typeof ChatComposerSurface>) => <>
    <button onClick={() => props.onSend({ text: "New question", paperMentions: [] })} disabled={props.disabled || props.busy}>Send test prompt</button>
    {props.busy && <button onClick={props.onStop}>Stop selected turn</button>}
    <output data-testid="draft">{props.draft?.text}</output>
  </>,
}));
vi.mock("@/components/chat/ChatConversation", () => ({
  ChatConversation: ({ messages, busy }: ComponentProps<typeof ChatConversation>) => {
    const location = useLocation();
    mocks.frames.push({ path: location.pathname, text: JSON.stringify(messages) });
    return <div data-testid="transcript" data-busy={busy}>
    {messages.map((message) => <div key={message.id}>{message.text}{message.blocks?.map((block, index) => (
      <span key={index}>{block.kind === "answer" ? block.text : ""}</span>
    ))}</div>)}
  </div>;
  },
}));
vi.mock("@/components/chat/useArtifactPanel", () => ({
  ArtifactPanelProvider: ({ children }: { children: ReactNode }) => children,
  canNavigateAwayFromArtifact: () => true,
}));
vi.mock("@/components/chat/ArtifactWorkspace", () => ({ ArtifactWorkspace: ({ children }: { children: ReactNode }) => children }));
vi.mock("@/components/chat/LatexPaperArtifact", () => ({ LatexPaperArtifact: ({ descriptor }: { descriptor: { title: string } }) => <aside>{descriptor.title}</aside> }));
vi.mock("@/components/chat/ChatSharing", () => ({ ChatSharing: () => null }));
import ChatView from "@/views/ChatView";
import { chatApi } from "@/lib/api/chat";
import { ApiError } from "@/lib/apiTransport";

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => { resolve = next; });
  return { promise, resolve };
};
const detail = (id: string, text = `${id} saved question`): ChatSessionDetail => ({
  id, title: `${id} title`, selected_model: "gpt-5.6-luna@openai",
  created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z",
  message_count: 1, is_busy: false, web_search_enabled: false,
  reasoning_effort: "low", transcript_status: "ready",
  messages: [{ id: `${id}-user`, turn_id: `${id}-turn`, sequence: 1, role: "user", content: text,
    revision: 1, status: "complete", display_blocks: [], citations: [], followups: [], error_code: null }],
});
const Probe = () => {
  const navigate = useNavigate();
  const location = useLocation();
  return <>
    <output data-testid="route">{location.pathname}</output>
    <output data-testid="search">{location.search}</output>
    {["a", "b", "missing"].map((id) => <button key={id} onClick={() => navigate(`/chat/${id}`)}>Visit {id}</button>)}
    <button onClick={() => navigate("/chat")}>Visit new</button>
  </>;
};
let client: QueryClient;
const element = (path: string) => <QueryClientProvider client={client}>
  <MemoryRouter initialEntries={[path]}><Routes><Route path="/chat/:sessionId?" element={<><ChatView /><Probe /></>} /></Routes></MemoryRouter>
</QueryClientProvider>;

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  mocks.user = { hf_subject: "owner", username: "owner" };
  mocks.authLoading = false;
  mocks.frames = [];
  mocks.getSession.mockImplementation(async (id: string) => detail(id));
  vi.spyOn(chatApi, "getSession").mockImplementation((id) => mocks.getSession(id));
  vi.spyOn(chatApi, "getModels").mockResolvedValue({ items: [{ id: "gpt-5.6-luna@openai", label: "Luna", provider: "openai" }], default_model: "gpt-5.6-luna@openai" });
  mocks.listSessions.mockResolvedValue([detail("a"), detail("b")]);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe("selected conversation and active turn ownership", () => {
  it("preserves a URL launch prompt and model while initial authentication loads", async () => {
    mocks.user = null;
    mocks.authLoading = true;
    mocks.stream.mockImplementation(async function* () {
      yield { type: "stream_start", session_id: "a", request_id: "r1" };
      await new Promise(() => undefined);
    });
    const path = "/chat?q=Launch%20question&model=gpt-5.6-luna%40openai";
    const view = render(element(path));
    expect(screen.getByTestId("search")).toHaveTextContent("q=Launch%20question");
    expect(mocks.stream).not.toHaveBeenCalled();
    mocks.user = { hf_subject: "owner", username: "owner" };
    mocks.authLoading = false;
    view.rerender(element(path));
    await waitFor(() => expect(mocks.stream).toHaveBeenCalledOnce());
    expect(mocks.stream.mock.calls[0][0]).toMatchObject({
      message: "Launch question", initial_model: "gpt-5.6-luna@openai",
    });
  });

  it("buffers a background answer and scopes title, artifact, and busy state when returning", async () => {
    const background = deferred<void>();
    const finish = deferred<void>();
    mocks.stream.mockImplementation(async function* () {
      yield { type: "stream_start", session_id: "a", request_id: "r1" };
      yield { type: "answer_delta", text: "First chunk" };
      await background.promise;
      yield { type: "session_title_done", title: "Streamed A title" };
      yield { type: "paper_artifact", descriptor: { artifact_id: "artifact-a", title: "A paper artifact" } };
      yield { type: "answer_delta", text: " plus background chunk" };
      await finish.promise;
      yield { type: "done", followups: [], finish_reason: "success" };
    });
    render(element("/chat/a"));
    await screen.findByText("a saved question");
    fireEvent.click(screen.getByText("Send test prompt"));
    await screen.findByText("First chunk");
    fireEvent.click(screen.getByText("Visit b"));
    await screen.findByText("b saved question");
    expect(screen.queryByText("Stop selected turn")).not.toBeInTheDocument();
    await act(async () => background.resolve());
    expect(screen.getByTestId("transcript")).toHaveTextContent("b saved question");
    expect(screen.queryByText("A paper artifact")).not.toBeInTheDocument();
    expect(document.querySelector(".chat-topbar-title")).toHaveTextContent("b title");
    mocks.frames = [];
    fireEvent.click(screen.getByText("Visit a"));
    await screen.findByText("First chunk plus background chunk");
    expect(mocks.frames.filter(frame => frame.path === "/chat/a")
      .some(frame => frame.text.includes("b saved question"))).toBe(false);
    expect(screen.getByText("Stop selected turn")).toBeInTheDocument();
    expect(screen.getByText("A paper artifact")).toBeInTheDocument();
    expect(document.querySelector(".chat-topbar-title")).toHaveTextContent("Streamed A title");
    expect(mocks.stream).toHaveBeenCalledTimes(1);
    await act(async () => finish.resolve());
    await waitFor(() => expect(screen.queryByText("Stop selected turn")).not.toBeInTheDocument());
  });

  it("a failed route load leaves the background turn alive and allows retry", async () => {
    const next = deferred<void>();
    mocks.stream.mockImplementation(async function* () {
      yield { type: "stream_start", session_id: "a", request_id: "r1" };
      await next.promise;
      yield { type: "answer_delta", text: "Still generating" };
      await new Promise(() => undefined);
    });
    mocks.getSession.mockImplementation(async (id: string) => {
      if (id === "missing") throw new Error("Conversation not found");
      return detail(id);
    });
    render(element("/chat/a"));
    await screen.findByText("a saved question");
    fireEvent.click(screen.getByText("Send test prompt"));
    await screen.findByText("Stop selected turn");
    fireEvent.click(screen.getByText("Visit missing"));
    await screen.findByText("Conversation not found");
    expect(screen.queryByTestId("transcript")).not.toBeInTheDocument();
    await act(async () => next.resolve());
    fireEvent.click(screen.getByText("Visit a"));
    await screen.findByText("Still generating");
    expect(mocks.stream).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText("Visit missing"));
    await screen.findByText("Conversation not found");
    mocks.getSession.mockImplementation(async (id: string) => detail(id));
    fireEvent.click(screen.getByText("Try again"));
    await screen.findByText("missing saved question");
  });

  it("late loads cannot replace the selected route and background admission cannot redirect it", async () => {
    const admitted = deferred<void>();
    const slow = deferred<ChatSessionDetail>();
    mocks.stream.mockImplementation(async function* () {
      await admitted.promise;
      yield { type: "stream_start", session_id: "a", request_id: "r1" };
      yield { type: "session_title_done", title: "New background title" };
      await new Promise(() => undefined);
    });
    mocks.getSession.mockImplementation((id: string) => id === "a" ? slow.promise : Promise.resolve(detail(id)));
    render(element("/chat"));
    fireEvent.click(screen.getByText("Send test prompt"));
    fireEvent.click(screen.getByText("Visit a"));
    await screen.findByText("Loading conversation…");
    fireEvent.click(screen.getByText("Visit b"));
    await screen.findByText("b saved question");
    await act(async () => {
      admitted.resolve();
      slow.resolve(detail("a", "Stale A response"));
    });
    expect(screen.getByTestId("route")).toHaveTextContent("/chat/b");
    expect(screen.getByTestId("transcript")).toHaveTextContent("b saved question");
    expect(screen.queryByText("Stale A response")).not.toBeInTheDocument();
  });

  it("follows new-session admission without refetching or dropping its transcript", async () => {
    const next = deferred<void>();
    mocks.listSessions.mockResolvedValue([]);
    mocks.stream.mockImplementation(async function* (): AsyncGenerator<ChatEvent> {
      yield { type: "stream_start", session_id: "a", request_id: "r1" };
      yield { type: "answer_delta", text: "Assigned session response" };
      await next.promise;
    });
    render(element("/chat"));
    fireEvent.click(screen.getByText("Send test prompt"));
    await screen.findByText("Assigned session response");
    expect(screen.getByTestId("route")).toHaveTextContent("/chat/a");
    expect(screen.getByText("Stop selected turn")).toBeInTheDocument();
    expect(mocks.getSession).not.toHaveBeenCalled();
    await act(async () => next.resolve());
    await waitFor(() => expect(mocks.getSession).toHaveBeenCalledTimes(1));
  });

  it("keeps a completed new conversation visible while its canonical reload is pending", async () => {
    const finish = deferred<void>();
    const canonical = deferred<ChatSessionDetail>();
    mocks.getSession.mockReturnValue(canonical.promise);
    mocks.stream.mockImplementation(async function* (): AsyncGenerator<ChatEvent> {
      yield { type: "stream_start", session_id: "a", request_id: "r1" };
      yield { type: "answer_delta", text: "Completed new answer" };
      await finish.promise;
      yield { type: "done", followups: [], finish_reason: "success" };
    });
    render(element("/chat"));
    fireEvent.click(screen.getByText("Send test prompt"));
    await screen.findByText("Completed new answer");
    await act(async () => finish.resolve());
    await waitFor(() => expect(mocks.getSession).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("transcript")).toHaveTextContent("Completed new answer");
    expect(screen.queryByText("Loading conversation…")).not.toBeInTheDocument();
    expect(screen.queryByText("Stop selected turn")).not.toBeInTheDocument();
    await act(async () => canonical.resolve(detail("a", "Canonical completed conversation")));
    await screen.findByText("Canonical completed conversation");
  });

  it("refreshes a cached saved conversation before projecting it on return", async () => {
    render(element("/chat/a"));
    await screen.findByText("a saved question");
    fireEvent.click(screen.getByText("Visit b"));
    await screen.findByText("b saved question");
    const refreshed = deferred<ChatSessionDetail>();
    mocks.getSession.mockReturnValue(refreshed.promise);
    fireEvent.click(screen.getByText("Visit a"));
    await screen.findByText("Loading conversation…");
    expect(screen.queryByText("b saved question")).not.toBeInTheDocument();
    await act(async () => refreshed.resolve(detail("a", "Freshly saved A")));
    await screen.findByText("Freshly saved A");
  });

  it("a pending history response cannot erase an admitted session", async () => {
    const history = deferred<ChatSessionDetail[]>();
    mocks.listSessions.mockReturnValue(history.promise);
    mocks.stream.mockImplementation(async function* () {
      yield { type: "stream_start", session_id: "a", request_id: "r1" };
      yield { type: "session_title_done", title: "Admitted chat" };
      yield { type: "answer_delta", text: "Active answer" };
      await new Promise(() => undefined);
    });
    render(element("/chat"));
    fireEvent.click(screen.getByText("Send test prompt"));
    await screen.findByText("Admitted chat", { selector: ".chat-session-title" });
    await act(async () => history.resolve([]));
    expect(screen.getByText("Admitted chat", { selector: ".chat-session-title" })).toBeInTheDocument();
    expect(screen.getByText("Stop selected turn")).toBeInTheDocument();
  });

  it("isolates cached transcripts and in-memory selection when accounts change", async () => {
    const rendered = render(element("/chat/a"));
    await screen.findByText("a saved question");
    const other = deferred<ChatSessionDetail>();
    mocks.getSession.mockReturnValue(other.promise);
    mocks.listSessions.mockResolvedValue([]);
    mocks.user = { hf_subject: "other-owner", username: "other-owner" };
    rendered.rerender(element("/chat/a"));
    expect(screen.queryByText("a saved question")).not.toBeInTheDocument();
    await act(async () => other.resolve(detail("a", "Other account conversation")));
    await screen.findByText("Other account conversation");
  });
});

describe("chat URLs opened by someone other than the owner", () => {
  const shareElement = (path: string) => <QueryClientProvider client={client}>
    <MemoryRouter initialEntries={[path]}><Routes>
      <Route path="/chat/:sessionId?" element={<ChatView />} />
      <Route path="/share/:shareId" element={<Probe />} />
    </Routes></MemoryRouter>
  </QueryClientProvider>;
  const notFound = () => new ApiError(new Response(null, { status: 404 }), "{}");

  it("sends a signed-out visitor to the public share", async () => {
    mocks.user = null;
    const lookup = vi.spyOn(chatApi, "getSessionPublicShare").mockResolvedValue({
      share_id: "s1", public_path: "/share/s1",
      created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z",
    });
    render(shareElement("/chat/a"));
    await waitFor(() => expect(screen.getByTestId("route")).toHaveTextContent("/share/s1"));
    expect(lookup).toHaveBeenCalledWith("a");
    expect(mocks.getSession).not.toHaveBeenCalled();
  });

  it("sends a signed-in non-owner to the public share", async () => {
    mocks.getSession.mockRejectedValue(notFound());
    vi.spyOn(chatApi, "getSessionPublicShare").mockResolvedValue({
      share_id: "s1", public_path: "/share/s1",
      created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z",
    });
    render(shareElement("/chat/a"));
    await waitFor(() => expect(screen.getByTestId("route")).toHaveTextContent("/share/s1"));
  });

  it("keeps the owner on their chat without looking up a share", async () => {
    const lookup = vi.spyOn(chatApi, "getSessionPublicShare");
    render(shareElement("/chat/a"));
    await screen.findByText("a saved question");
    expect(lookup).not.toHaveBeenCalled();
  });

  it("shows the load error when the chat was never shared", async () => {
    mocks.getSession.mockRejectedValue(notFound());
    vi.spyOn(chatApi, "getSessionPublicShare").mockRejectedValue(notFound());
    render(shareElement("/chat/a"));
    await screen.findByRole("alert");
  });
});

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import Composer from "@/components/chat/Composer";
import { AssistantMessage, UserMessage } from "@/components/chat/ChatMessage";
import { PanelIcon, PlusIcon, Spinner, TrashIcon } from "@/components/chat/icons";
import { useChat } from "@/hooks/useChat";
import { isChatLive } from "@/lib/chat";
import {
  CHAT_AUTO_SEND_KEY,
  CHAT_DRAFT_KEY,
  CHAT_MODEL_KEY,
  clearQueuedChatLaunch,
  readQueuedChatLaunch,
} from "@/lib/chatLaunch";
import { apiUrl } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";
import {
  DEFAULT_CHAT_MODEL,
  FALLBACK_CHAT_MODELS,
  type ChatModelChoice,
  type ChatSession,
  getChatModels,
  getSession,
  groupSessions,
  listSessions,
  removeSession,
  toUiMessages,
  updateSession,
} from "@/lib/chatSessions";

const EXAMPLES = [
  "What's the state of the art for real-time object detection?",
  "Recommend recent papers on retrieval-augmented generation",
  "Which open LLMs are best for on-device inference?",
];

type RouteSessionState = {
  id: string;
  status: "loading" | "loaded" | "error";
  error?: string;
};

const ChatView: React.FC = () => {
  const { sessionId: routeSessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, isLoading: authLoading } = useAuth();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionError, setSessionError] = useState("");
  const [routeSessionState, setRouteSessionState] = useState<RouteSessionState | null>(
    () => routeSessionId ? { id: routeSessionId, status: "loading" } : null,
  );
  const [routeLoadAttempt, setRouteLoadAttempt] = useState(0);
  const queuedLaunchRef = useRef(readQueuedChatLaunch());
  const requestedModelRef = useRef(searchParams.get("model") || queuedLaunchRef.current?.model);
  const [models, setModels] = useState<ChatModelChoice[]>(FALLBACK_CHAT_MODELS);
  const [selectedModel, setSelectedModel] = useState(
    requestedModelRef.current || DEFAULT_CHAT_MODEL,
  );
  const [liveTitle, setLiveTitle] = useState("");
  const [draft, setDraft] = useState("");
  const [pendingAutoPrompt, setPendingAutoPrompt] = useState(
    () => searchParams.get("q")?.trim() || queuedLaunchRef.current?.prompt || "",
  );
  const autoSendStartedRef = useRef(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [sessionMenu, setSessionMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(() => typeof window === "undefined" || window.innerWidth > 900);
  const manualTitleLockRef = useRef<Set<string>>(new Set());
  const sessionsLoadedRef = useRef(false);
  const routeSessionIdRef = useRef(routeSessionId);
  const loadedRouteSessionIdRef = useRef<string | null>(null);
  routeSessionIdRef.current = routeSessionId;

  const refreshSessions = useCallback(async () => {
    if (!user) return;
    const showLoading = !sessionsLoadedRef.current;
    if (showLoading) setSessionsLoading(true);
    try {
      setSessions(await listSessions());
      sessionsLoadedRef.current = true;
      setSessionError("");
    } catch (error) {
      setSessionError(error instanceof Error ? error.message : "Could not load chats");
    } finally {
      if (showLoading) setSessionsLoading(false);
    }
  }, [user]);

  const chat = useChat({
    sessionId: routeSessionId ?? null,
    initialModel: selectedModel,
    onSessionId: (id) => {
      // A newly created session is already present in local state; do not hide
      // its in-progress response behind the saved-session loading screen.
      loadedRouteSessionIdRef.current = id;
      setRouteSessionState({ id, status: "loaded" });
      navigate(`/chat/${id}`, { replace: true });
    },
    onTitle: (title) => {
      if (routeSessionId && !manualTitleLockRef.current.has(routeSessionId)) {
        setLiveTitle(title);
        setSessions((previous) => previous.map((session) => session.id === routeSessionId ? { ...session, title } : session));
      }
    },
    onSettled: () => {
      void refreshSessions();
      if (routeSessionId) {
        void getSession(routeSessionId).then((detail) => chat.load(toUiMessages(detail)));
      }
    },
    onInterrupted: (text) => {
      setDraft(text);
      if (routeSessionId) window.setTimeout(() => { void getSession(routeSessionId).then((detail) => chat.load(toUiMessages(detail))); }, 450);
    },
  });
  const loadChat = chat.load;
  const sendChat = chat.send;

  const send = useCallback((text: string) => {
    if (!user) {
      sessionStorage.setItem(CHAT_DRAFT_KEY, text);
      sessionStorage.setItem(CHAT_MODEL_KEY, selectedModel);
      sessionStorage.setItem(CHAT_AUTO_SEND_KEY, "1");
      window.location.href = apiUrl(`/api/v1/auth/hf/login?return_to=${encodeURIComponent("/chat")}`);
      return;
    }
    if (!sendChat(text)) return;
    clearQueuedChatLaunch();
    setDraft("");
  }, [selectedModel, sendChat, user]);

  useEffect(() => {
    if (authLoading || !user) return;
    const savedModel = sessionStorage.getItem(CHAT_MODEL_KEY);
    if (savedModel) setSelectedModel(savedModel);
    void refreshSessions();
    void getChatModels().then((result) => {
      setModels(result.items);
      if (!routeSessionIdRef.current) {
        const requestedModel = requestedModelRef.current || savedModel;
        setSelectedModel(
          requestedModel && result.items.some((model) => model.id === requestedModel)
            ? requestedModel
            : result.default_model,
        );
      }
    });
    const savedDraft = sessionStorage.getItem(CHAT_DRAFT_KEY);
    const shouldAutoSend = sessionStorage.getItem(CHAT_AUTO_SEND_KEY) === "1";
    if (savedDraft) {
      if (shouldAutoSend) setPendingAutoPrompt(savedDraft);
      else setDraft(savedDraft);
    }
  }, [authLoading, refreshSessions, user]);

  useEffect(() => {
    if (!routeSessionId) {
      // Do not reset an already-new chat when its request flips `busy` to
      // true. This effect also watches `chat.busy` so saved routes can load
      // after an in-flight turn settles; resetting unconditionally here
      // aborted brand-new turns before their first SSE event arrived.
      if (loadedRouteSessionIdRef.current !== null) {
        loadedRouteSessionIdRef.current = null;
        chat.reset();
      }
      setRouteSessionState(null);
      return;
    }
    if (loadedRouteSessionIdRef.current === routeSessionId) return;
    setRouteSessionState((previous) => previous?.id === routeSessionId && previous.status === "loading"
      ? previous
      : { id: routeSessionId, status: "loading" });
    if (authLoading || !user || chat.busy) return;

    let cancelled = false;
    setSessionError("");
    void getSession(routeSessionId).then((detail) => {
      if (cancelled) return;
      chat.load(toUiMessages(detail));
      setSelectedModel(detail.selected_model);
      setLiveTitle(detail.title);
      loadedRouteSessionIdRef.current = routeSessionId;
      setRouteSessionState({ id: routeSessionId, status: "loaded" });
    }).catch((error) => {
      if (cancelled) return;
      const message = error instanceof Error ? error.message : "Chat not found";
      chat.reset();
      setSessionError(message);
      setRouteSessionState({ id: routeSessionId, status: "error", error: message });
    });
    return () => { cancelled = true; };
    // Loading is intentionally keyed to the route, not streaming state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, routeSessionId, user, chat.busy, routeLoadAttempt]);

  useEffect(() => {
    const prompt = searchParams.get("q")?.trim();
    if (!prompt) return;
    autoSendStartedRef.current = false;
    const requestedModel = searchParams.get("model");
    if (requestedModel) setSelectedModel(requestedModel);
    setPendingAutoPrompt(prompt);
    const next = new URLSearchParams(searchParams);
    next.delete("q");
    next.delete("model");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (authLoading || chat.busy || !pendingAutoPrompt || autoSendStartedRef.current) return;
    // Deferring avoids React StrictMode's development-only effect cleanup from
    // aborting the request before the second effect pass can own it.
    const timer = window.setTimeout(() => {
      if (autoSendStartedRef.current) return;
      autoSendStartedRef.current = true;
      const prompt = pendingAutoPrompt;
      setPendingAutoPrompt("");
      send(prompt);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [authLoading, chat.busy, pendingAutoPrompt, send]);

  useEffect(() => {
    const onFocus = () => {
      if (!user || chat.busy) return;
      void refreshSessions();
      if (routeSessionId) {
        void getSession(routeSessionId).then((detail) => loadChat(toUiMessages(detail)));
      }
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [chat.busy, loadChat, refreshSessions, routeSessionId, user]);

  useEffect(() => {
    if (!sessionMenu) return;
    const close = () => setSessionMenu(null);
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") close(); };
    window.addEventListener("click", close);
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("click", close); window.removeEventListener("keydown", onKey); };
  }, [sessionMenu]);

  const newChat = () => { chat.reset(); setDraft(""); setLiveTitle(""); navigate("/chat"); };
  const saveRename = async (id: string) => {
    const title = editingTitle.trim();
    if (!title) return;
    try {
      const updated = await updateSession(id, { title });
      manualTitleLockRef.current.add(id);
      if (id === routeSessionId) setLiveTitle(updated.title);
      setSessions((previous) => previous.map((session) => session.id === id ? updated : session));
      setEditingId(null);
    } catch (error) { setSessionError(error instanceof Error ? error.message : "Rename failed"); }
  };
  const remove = async (id: string) => {
    const active = id === routeSessionId && chat.busy;
    if (!window.confirm(active ? "Stop and delete this chat? This cannot be undone." : "Delete this chat? This cannot be undone.")) return;
    if (active) chat.stop();
    try {
      if (active) {
        const deadline = Date.now() + 3_000;
        for (;;) {
          const detail = await getSession(id);
          if (!detail.is_busy) break;
          if (Date.now() >= deadline) throw new Error("Generation is still stopping. The chat was not deleted.");
          await new Promise((resolve) => window.setTimeout(resolve, 150));
        }
      }
      await removeSession(id); if (id === routeSessionId) newChat(); await refreshSessions();
    }
    catch (error) { setSessionError(error instanceof Error ? error.message : "Delete failed"); }
  };
  const changeModel = async (model: string) => {
    const previousModel = selectedModel;
    setSelectedModel(model);
    if (!routeSessionId) return;
    try {
      const updated = await updateSession(routeSessionId, { selected_model: model });
      setSessions((previous) => previous.map((session) => session.id === routeSessionId
        ? { ...session, selected_model: updated.selected_model }
        : session));
      setSessionError("");
    }
    catch (error) { setSelectedModel(previousModel); setSessionError(error instanceof Error ? error.message : "Model change failed"); }
  };

  const [headerHeight, setHeaderHeight] = useState(60);
  useLayoutEffect(() => {
    const element = document.querySelector<HTMLElement>(".app-header");
    if (!element) return;
    const update = () => setHeaderHeight(element.offsetHeight);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollTopBeforeToggleRef = useRef<number | null>(null);
  const toggleBlock = (messageId: string, blockIndex: number) => {
    scrollTopBeforeToggleRef.current = scrollRef.current?.scrollTop ?? null;
    chat.toggleBlock(messageId, blockIndex);
  };
  useLayoutEffect(() => {
    const scrollElement = scrollRef.current;
    if (!scrollElement) return;
    if (scrollTopBeforeToggleRef.current !== null) {
      scrollElement.scrollTop = scrollTopBeforeToggleRef.current;
      scrollTopBeforeToggleRef.current = null;
      return;
    }
    scrollElement.scrollTop = scrollElement.scrollHeight;
  }, [chat.messages]);

  const current = sessions.find((session) => session.id === routeSessionId);
  const isEmpty = chat.messages.length === 0;
  const routeStateMatches = routeSessionState?.id === routeSessionId;
  const isRouteSessionLoading = Boolean(routeSessionId && (
    authLoading || (user && (!routeStateMatches || routeSessionState?.status === "loading"))
  ));
  const routeSessionError = routeStateMatches && routeSessionState?.status === "error"
    ? routeSessionState.error
    : undefined;

  return (
    <div className="chat-page" style={{ height: `calc(100dvh - ${headerHeight}px)` }}>
      <aside className={`chat-sidebar${sidebarOpen ? "" : " chat-sidebar-closed"}`}>
        <div className="chat-sidebar-top">
          <button type="button" className="chat-new-chat" onClick={newChat}><PlusIcon /> New chat</button>
          <button type="button" className="icon-btn" onClick={() => setSidebarOpen(false)} title="Collapse sidebar"><PanelIcon /></button>
        </div>
        <nav className="chat-sessions" aria-label="Chat history">
          {sessionsLoading && <div className="chat-sessions-empty">Loading chats…</div>}
          {!sessionsLoading && sessionError && <div className="chat-sessions-empty">{sessionError}</div>}
          {!sessionsLoading && !sessionError && sessions.length === 0 && <div className="chat-sessions-empty">Conversations you start will show up here.</div>}
          {groupSessions(sessions).map((group) => <div className="chat-session-group" key={group.label}>
            <div className="chat-session-group-label">{group.label}</div>
            {group.items.map((session) => <div
              key={session.id}
              className={`chat-session${session.id === routeSessionId ? " chat-session-active" : ""}`}
              role="button" tabIndex={0}
              onClick={() => navigate(`/chat/${session.id}`)}
              onKeyDown={(event) => {
                if (event.key === "Enter") navigate(`/chat/${session.id}`);
                if (event.key === "F2") { setEditingId(session.id); setEditingTitle(session.title); }
                if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
                  event.preventDefault();
                  const rect = event.currentTarget.getBoundingClientRect();
                  setSessionMenu({ id: session.id, x: rect.right - 150, y: rect.bottom });
                }
              }}
              onContextMenu={(event) => { event.preventDefault(); setSessionMenu({ id: session.id, x: event.clientX, y: event.clientY }); }}
            >
              {editingId === session.id ? <input
                className="chat-session-title-input" value={editingTitle} autoFocus maxLength={80}
                onClick={(event) => event.stopPropagation()}
                onChange={(event) => setEditingTitle(event.target.value)}
                onBlur={() => void saveRename(session.id)}
                onKeyDown={(event) => { event.stopPropagation(); if (event.key === "Enter") void saveRename(session.id); if (event.key === "Escape") setEditingId(null); }}
              /> : <span className="chat-session-title">{session.title}</span>}
              <button type="button" className="chat-session-menu" aria-label="Chat actions" aria-haspopup="menu" title="Chat actions" onClick={(event) => { event.stopPropagation(); const rect = event.currentTarget.getBoundingClientRect(); setSessionMenu({ id: session.id, x: rect.right - 150, y: rect.bottom }); }}>⋯</button>
              <button type="button" className="chat-session-delete" aria-label="Delete conversation" onClick={(event) => { event.stopPropagation(); void remove(session.id); }}><TrashIcon /></button>
            </div>)}
          </div>)}
        </nav>
        {sessionMenu && <div className="chat-session-context-menu" role="menu" style={{ left: sessionMenu.x, top: sessionMenu.y }} onClick={(event) => event.stopPropagation()}>
          <button type="button" role="menuitem" autoFocus onClick={() => {
            const session = sessions.find((item) => item.id === sessionMenu.id);
            if (session) { setEditingId(session.id); setEditingTitle(session.title); }
            setSessionMenu(null);
          }}>Rename chat</button>
        </div>}
      </aside>

      <section className="chat-main">
        <div className="chat-topbar">
          {!sidebarOpen && <button type="button" className="icon-btn" onClick={() => setSidebarOpen(true)} title="Open sidebar"><PanelIcon /></button>}
          <span className="chat-topbar-title">{isRouteSessionLoading
            ? current?.title || ""
            : liveTitle || current?.title || (isEmpty ? "" : "New chat")}</span>
        </div>

        {isRouteSessionLoading ? <div className="chat-session-loading" role="status" aria-live="polite">
          <Spinner />
          <span>Loading conversation…</span>
        </div> : routeSessionError ? <div className="chat-session-load-error" role="alert">
          <p>{routeSessionError}</p>
          <button type="button" onClick={() => {
            setRouteSessionState({ id: routeSessionId!, status: "loading" });
            setRouteLoadAttempt((attempt) => attempt + 1);
          }}>Try again</button>
        </div> : isEmpty ? <div className="chat-empty"><div className="chat-empty-inner">
          <div className="chat-empty-eyebrow">AI research assistant · Staging preview</div>
          <h1 className="chat-empty-title">Ask <em>Papers With Code</em></h1>
          <p className="chat-empty-sub">Answers are grounded in a live hybrid search over papers, tasks, and benchmarks — with citations you can follow.</p>
          <Composer onSend={send} busy={chat.busy} onStop={chat.stop} autoFocus draft={draft} onDraftChange={setDraft} models={models} selectedModel={selectedModel} onModelChange={(model) => void changeModel(model)} />
          <div className="chat-examples">{EXAMPLES.map((example) => <button type="button" key={example} className="chat-example" onClick={() => send(example)}>{example}</button>)}</div>
        </div></div> : <>
          <div className="chat-conversation" ref={scrollRef}><div className="chat-conversation-inner">
            {chat.messages.map((message) => message.role === "user"
              ? <UserMessage key={message.id} text={message.text ?? ""} />
              : <AssistantMessage key={message.id} msg={message} papers={chat.papers} onToggleBlock={toggleBlock} />)}
          </div></div>
          <div className="chat-composer-wrap"><div className="chat-composer-inner">
            <Composer onSend={send} busy={chat.busy} onStop={chat.stop} placeholder={draft ? "Edit and send again…" : "Ask a follow-up…"} draft={draft} onDraftChange={setDraft} models={models} selectedModel={selectedModel} onModelChange={(model) => void changeModel(model)} />
            <div className="chat-composer-foot">{isChatLive() ? <>
              <span className="chat-provider-attribution">Powered by 🤗 <a href="https://huggingface.co/docs/inference-providers/en/index" target="_blank" rel="noreferrer">Inference Providers</a>.</span>
              <span>The AI assistant can make mistakes. Double-check responses.</span>
            </> : <>Assistant preview — responses are simulated.</>}</div>
          </div></div>
        </>}
      </section>
    </div>
  );
};

export default ChatView;

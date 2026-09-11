import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ChatComposerSurface } from "@/components/chat/ChatComposerSurface";
import { ChatConversation } from "@/components/chat/ChatConversation";
import {
  ChatCapacityDialog,
  ChatDisabledDialog,
} from "@/components/chat/ChatDialogs";
import { ChatSessionNavigation } from "@/components/chat/ChatSessionNavigation";
import { ChatSharing } from "@/components/chat/ChatSharing";
import { ArtifactWorkspace } from "@/components/chat/ArtifactWorkspace";
import { LatexPaperArtifact } from "@/components/chat/LatexPaperArtifact";
import { ArtifactPanelProvider, canNavigateAwayFromArtifact } from "@/components/chat/useArtifactPanel";
import { useChatArchive } from "@/components/chat/useChatArchive";
import { PanelIcon, Spinner } from "@/components/chat/icons";
import { hfLoginUrl } from "@/components/HfSignInButton";
import { useChat } from "@/hooks/useChat";
import { isChatLive, type ChatDraft, type PaperSelectionDraft, type ReasoningEffort } from "@/lib/chat";
import {
  CHAT_AUTO_SEND_KEY,
  CHAT_AUTH_ATTEMPTED_KEY,
  CHAT_DRAFT_KEY,
  CHAT_MODEL_KEY,
  CHAT_REASONING_EFFORT_KEY,
  clearQueuedChatLaunch,
  readQueuedChatLaunch,
} from "@/lib/chatLaunch";
import { SUGGESTED_CHAT_PROMPTS } from "@/lib/chatPrompts";
import { emptyChatDraft, parseChatDraft } from "@/lib/paperSelection";
import { chatApi } from "@/lib/api/chat";
import { isStagingEnvironment } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";
import {
  OPENROUTER_CREDENTIAL_QUERY_KEY,
  useOpenRouterCredential,
} from "@/lib/openrouter";
import {
  DEFAULT_CHAT_MODEL,
  PRODUCTION_FALLBACK_CHAT_MODELS,
  STAGING_FALLBACK_CHAT_MODELS,
  type ChatModelChoice,
  type LatexPaperArtifactDescriptor,
  type ChatSession,
  getChatModels,
  getSession,
  listSessions,
  providerForChatModel,
  removeSession,
  toUiMessages,
  updateSession,
} from "@/lib/chatSessions";

const emptyDraft = emptyChatDraft;
const READER_PROMPTS = [
  "Summarize the main contributions",
  "Explain in simple terms",
  "Identify the main limitations",
];
const readStoredDraft = (): ChatDraft | null => {
  const raw = sessionStorage.getItem(CHAT_DRAFT_KEY);
  if (!raw) return null;
  try {
    return parseChatDraft(JSON.parse(raw), raw);
  } catch { /* Legacy storage contained only the text. */ }
  return emptyDraft(raw);
};

type RouteSessionState = {
  id: string;
  status: "loading" | "loaded" | "error";
  error?: string;
};

export interface ChatExperienceProps {
  mode?: "general" | "paper";
  routeSessionId?: string;
  primaryPaper?: { id: string; routeId: string; title: string };
  currentPage?: () => number;
  paperSelection?: PaperSelectionDraft;
  onPaperSelectionChange?: (selection?: PaperSelectionDraft) => void;
  onSessionId?: (sessionId: string) => void;
  onReaderSubmit?: () => void;
  onReaderNewChat?: () => void;
}

const GeneralArtifactProvider: React.FC<{
  enabled: boolean;
  workspaceKey: string;
  children: React.ReactNode;
  onAskAiFix?: (prompt: string) => void;
}> = ({ enabled, workspaceKey, children, onAskAiFix }) => enabled
  ? <ArtifactPanelProvider workspaceKey={workspaceKey} onAskAiFix={onAskAiFix}>{children}</ArtifactPanelProvider>
  : <>{children}</>;

const GeneralArtifactWorkspace: React.FC<{
  enabled: boolean;
  children: React.ReactNode;
}> = ({ enabled, children }) => enabled
  ? <ArtifactWorkspace variant="chat">{children}</ArtifactWorkspace>
  : <>{children}</>;

export const ChatExperience: React.FC<ChatExperienceProps> = ({
  mode = "general",
  routeSessionId: suppliedSessionId,
  primaryPaper,
  currentPage,
  paperSelection,
  onPaperSelectionChange,
  onSessionId: onReaderSessionId,
  onReaderSubmit,
  onReaderNewChat,
}) => {
  const { sessionId: paramSessionId } = useParams<{ sessionId: string }>();
  const routeSessionId = suppliedSessionId ?? (mode === "general" ? paramSessionId : undefined);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, isLoading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  const staging = isStagingEnvironment();
  const availabilityQuery = useQuery({
    queryKey: ["chatAvailability"],
    queryFn: () => chatApi.getAvailability(),
    refetchInterval: 30000,
    retry: false,
    enabled: isChatLive() && Boolean(user),
  });
  const chatPaused = availabilityQuery.data?.status === "paused"
    || (mode === "paper" && availabilityQuery.data?.paper_reader_chat_enabled === false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionError, setSessionError] = useState("");
  const [routeSessionState, setRouteSessionState] = useState<RouteSessionState | null>(
    () => routeSessionId ? { id: routeSessionId, status: "loading" } : null,
  );
  const [routeLoadAttempt, setRouteLoadAttempt] = useState(0);
  const [latexPaper, setLatexPaper] = useState<LatexPaperArtifactDescriptor | null>(null);
  const queuedLaunchRef = useRef(readQueuedChatLaunch());
  const requestedModelRef = useRef(searchParams.get("model") || queuedLaunchRef.current?.model);
  const [models, setModels] = useState<ChatModelChoice[]>(
    staging ? STAGING_FALLBACK_CHAT_MODELS : PRODUCTION_FALLBACK_CHAT_MODELS,
  );
  const [selectedModel, setSelectedModel] = useState(
    requestedModelRef.current || DEFAULT_CHAT_MODEL,
  );
  const selectedProvider = providerForChatModel(models, selectedModel);
  const openRouterCredentialQuery = useOpenRouterCredential(
    Boolean(user && selectedProvider === "openrouter"),
  );
  const selectedProviderRef = useRef(selectedProvider);
  selectedProviderRef.current = selectedProvider;
  const [liveTitle, setLiveTitle] = useState("");
  const [routeViewerPage, setRouteViewerPage] = useState<number | null>(null);
  const [draft, setDraft] = useState<ChatDraft>(() => emptyDraft());
  const [webSearchEnabled, setWebSearchEnabled] = useState(
    () => queuedLaunchRef.current?.webSearchEnabled ?? false,
  );
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>(
    () => queuedLaunchRef.current?.reasoningEffort ?? "low",
  );
  const webSearchAvailable = Boolean(availabilityQuery.data?.web_search_available);
  const [pendingAutoDraft, setPendingAutoDraft] = useState<ChatDraft>(() => {
    const queryPrompt = searchParams.get("q")?.trim();
    if (queryPrompt) return emptyDraft(queryPrompt);
    return queuedLaunchRef.current?.draft ?? emptyDraft();
  });
  const autoSendStartedRef = useRef(false);
  const inferenceConnectedRef = useRef(false);
  const inferenceCheckPendingRef = useRef(false);
  const [sidebarOpen, setSidebarOpen] = useState(() => typeof window === "undefined" || window.innerWidth > 900);
  const manualTitleLockRef = useRef<Set<string>>(new Set());
  const sessionsLoadedRef = useRef(false);
  const routeSessionIdRef = useRef(routeSessionId);
  const activeStreamSessionIdRef = useRef<string | null>(null);
  const activeStreamRouteSessionIdRef = useRef<string | null>(null);
  const loadedRouteSessionIdRef = useRef<string | null>(null);
  routeSessionIdRef.current = routeSessionId;

  const refreshSessions = useCallback(async () => {
    if (!user) return;
    const showLoading = !sessionsLoadedRef.current;
    if (showLoading) setSessionsLoading(true);
    try {
      const fetched = await listSessions();
      setSessions((previous) => {
        const activeId = activeStreamSessionIdRef.current;
        const active = activeId ? previous.find((session) => session.id === activeId) : undefined;
        if (!active) return fetched;
        const saved = fetched.find((session) => session.id === activeId);
        const inProgress = saved ? { ...saved, title: active.title, is_busy: true } : active;
        return [inProgress, ...fetched.filter((session) => session.id !== activeId)];
      });
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
    webSearchEnabled: webSearchAvailable && webSearchEnabled,
    reasoningEffort,
    primaryPaperRouteId: mode === "paper" ? primaryPaper?.routeId : undefined,
    viewerContext: mode === "paper" && currentPage
      ? () => ({ page: Math.max(1, Math.min(10_000, currentPage())) })
      : undefined,
    onSessionId: (id) => {
      activeStreamSessionIdRef.current = id;
      const isNewSession = id !== routeSessionIdRef.current;
      const shouldFollowStream = (
        routeSessionIdRef.current ?? null
      ) === activeStreamRouteSessionIdRef.current;
      const now = new Date().toISOString();
      setSessions((previous) => previous.some((session) => session.id === id)
        ? previous.map((session) => session.id === id ? { ...session, is_busy: true } : session)
        : [{
            id,
            title: "New chat",
            selected_model: selectedModel,
            created_at: now,
            updated_at: now,
            message_count: 1,
            is_busy: true,
            web_search_enabled: webSearchEnabled,
            reasoning_effort: reasoningEffort,
          }, ...previous]);
      if (isNewSession && shouldFollowStream) {
        setLiveTitle("New chat");
      }
      if (shouldFollowStream) {
        // Keep the in-progress response visible while the route catches up with
        // the newly persisted session announced by the SSE stream.
        loadedRouteSessionIdRef.current = id;
        setRouteSessionState({ id, status: "loaded" });
        if (isNewSession) {
          if (mode === "paper") onReaderSessionId?.(id);
          else navigate(`/chat/${id}`, { replace: true });
        }
      }
    },
    onTitle: (title) => {
      const sessionId = activeStreamSessionIdRef.current ?? routeSessionIdRef.current;
      if (sessionId && !manualTitleLockRef.current.has(sessionId)) {
        if (sessionId === routeSessionIdRef.current) setLiveTitle(title);
        setSessions((previous) => previous.map((session) => session.id === sessionId ? { ...session, title } : session));
      }
    },
    onSettled: (sessionId) => {
      if (sessionId) {
        setSessions((previous) => previous.map((session) => session.id === sessionId
          ? { ...session, is_busy: false }
          : session));
      }
      activeStreamSessionIdRef.current = null;
      activeStreamRouteSessionIdRef.current = null;
      if (sessionId && mode === "general") {
        void getSession(sessionId).then((detail) => {
          if (routeSessionIdRef.current === sessionId) {
            setLatexPaper(detail.latex_paper ?? null);
          }
        }).catch(() => undefined);
      }
      void refreshSessions();
    },
    onProviderTerminal: () => {
      if (selectedProviderRef.current === "openrouter") {
        void queryClient.invalidateQueries({ queryKey: OPENROUTER_CREDENTIAL_QUERY_KEY });
      }
    },
    onPaperArtifact: (event) => {
      if (mode === "general") setLatexPaper(event.descriptor);
    },
    onInterrupted: (interruptedDraft) => {
      setDraft(interruptedDraft);
      onPaperSelectionChange?.(interruptedDraft.paperSelection);
    },
  });
  const sendChat = chat.send;

  useEffect(() => {
    if (!chat.capacityRequest) return;
    setDraft(chat.capacityRequest.draft);
    onPaperSelectionChange?.(chat.capacityRequest.draft.paperSelection);
  }, [chat.capacityRequest, onPaperSelectionChange]);

  const authorizeInference = useCallback((nextDraft: ChatDraft) => {
    sessionStorage.setItem(CHAT_DRAFT_KEY, JSON.stringify(nextDraft));
    sessionStorage.setItem(CHAT_MODEL_KEY, selectedModel);
    sessionStorage.setItem(CHAT_REASONING_EFFORT_KEY, reasoningEffort);
    sessionStorage.setItem(CHAT_AUTO_SEND_KEY, "1");
    sessionStorage.setItem(CHAT_AUTH_ATTEMPTED_KEY, "1");
    const returnTo = mode === "paper" && primaryPaper
      ? `/pdf/${primaryPaper.routeId}`
      : routeSessionIdRef.current
        ? `/chat/${routeSessionIdRef.current}`
        : "/chat";
    window.location.href = hfLoginUrl(returnTo, selectedProvider === "huggingface");
  }, [mode, primaryPaper, reasoningEffort, selectedModel, selectedProvider]);

  const restoreAuthorizationPrompt = useCallback((nextDraft: ChatDraft, message: string) => {
    sessionStorage.setItem(CHAT_DRAFT_KEY, JSON.stringify(nextDraft));
    sessionStorage.setItem(CHAT_MODEL_KEY, selectedModel);
    sessionStorage.removeItem(CHAT_AUTO_SEND_KEY);
    sessionStorage.removeItem(CHAT_AUTH_ATTEMPTED_KEY);
    setPendingAutoDraft(emptyDraft());
    setDraft(nextDraft);
    onPaperSelectionChange?.(nextDraft.paperSelection);
    setSessionError(message);
  }, [onPaperSelectionChange, selectedModel]);

  const send = useCallback(async (nextDraft: ChatDraft) => {
    const payload = onPaperSelectionChange
      ? (paperSelection ? { ...nextDraft, paperSelection } : { text: nextDraft.text, paperMentions: nextDraft.paperMentions })
      : nextDraft;
    if (!user) {
      authorizeInference(payload);
      return;
    }
    if (selectedProvider === "huggingface" && !inferenceConnectedRef.current) {
      if (inferenceCheckPendingRef.current) return;
      inferenceCheckPendingRef.current = true;
      try {
        const billing = await chatApi.getInferenceBilling();
        if (!billing.connected) {
          if (sessionStorage.getItem(CHAT_AUTH_ATTEMPTED_KEY) === "1") {
            restoreAuthorizationPrompt(
              payload,
              "Hugging Face inference authorization was not completed. Your prompt is ready to retry.",
            );
            return;
          }
          authorizeInference(payload);
          return;
        }
        inferenceConnectedRef.current = true;
      } catch (error) {
        restoreAuthorizationPrompt(
          payload,
          error instanceof Error
            ? error.message
            : "Could not check Hugging Face authorization.",
        );
        return;
      } finally {
        inferenceCheckPendingRef.current = false;
      }
    }
    const streamRouteSessionId = routeSessionIdRef.current ?? null;
    sessionStorage.removeItem(CHAT_AUTO_SEND_KEY);
    if (!sendChat(payload)) {
      restoreAuthorizationPrompt(
        payload,
        "Your prompt was not sent. It is ready to retry.",
      );
      return;
    }
    activeStreamRouteSessionIdRef.current = streamRouteSessionId;
    activeStreamSessionIdRef.current = streamRouteSessionId;
    sessionStorage.removeItem(CHAT_DRAFT_KEY);
    sessionStorage.removeItem(CHAT_MODEL_KEY);
    sessionStorage.removeItem(CHAT_AUTH_ATTEMPTED_KEY);
    clearQueuedChatLaunch();
    setDraft(emptyDraft());
    onPaperSelectionChange?.(undefined);
    if (mode === "paper") onReaderSubmit?.();
  }, [authorizeInference, mode, onPaperSelectionChange, onReaderSubmit, paperSelection, restoreAuthorizationPrompt, selectedProvider, sendChat, user]);

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
    const savedDraft = readStoredDraft();
    const shouldAutoSend = sessionStorage.getItem(CHAT_AUTO_SEND_KEY) === "1";
    if (savedDraft) {
      onPaperSelectionChange?.(savedDraft.paperSelection);
      if (shouldAutoSend) setPendingAutoDraft(savedDraft);
      else setDraft(savedDraft);
    }
  }, [authLoading, onPaperSelectionChange, refreshSessions, user]);

  useEffect(() => {
    if (!routeSessionId) {
      // Do not reset an already-new chat when its request flips `busy` to
      // true. This effect also watches `chat.busy` so saved routes can load
      // after an in-flight turn settles; resetting unconditionally here
      // aborted brand-new turns before their first SSE event arrived.
      if (loadedRouteSessionIdRef.current !== null && !chat.busy) {
        loadedRouteSessionIdRef.current = null;
        chat.reset();
        setWebSearchEnabled(false);
        setReasoningEffort("low");
      }
      setRouteSessionState(null);
      setRouteViewerPage(null);
      setLatexPaper(null);
      return;
    }
    if (loadedRouteSessionIdRef.current === routeSessionId) return;
    setRouteViewerPage(null);
    setRouteSessionState((previous) => previous?.id === routeSessionId && previous.status === "loading"
      ? previous
      : { id: routeSessionId, status: "loading" });
    if (authLoading || !user) return;

    let cancelled = false;
    setSessionError("");
    void getSession(routeSessionId).then((detail) => {
      if (cancelled) return;
      chat.load(toUiMessages(detail), routeSessionId, detail.is_busy);
      setLatexPaper(detail.latex_paper ?? null);
      setSelectedModel(detail.selected_model);
      setWebSearchEnabled(
        queuedLaunchRef.current && detail.messages.length === 0
          ? queuedLaunchRef.current.webSearchEnabled
          : detail.web_search_enabled,
      );
      setReasoningEffort(
        queuedLaunchRef.current && detail.messages.length === 0
          ? queuedLaunchRef.current.reasoningEffort
          : detail.reasoning_effort ?? "high",
      );
      setLiveTitle(detail.title);
      const latestViewerPage = [...detail.messages]
        .reverse()
        .find((message) => message.role === "user" && message.viewer_context)?.viewer_context?.page;
      setRouteViewerPage(latestViewerPage ?? null);
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
    // Loading is intentionally keyed to the route. `chat.load` detaches the
    // visible transcript without cancelling an active stream.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, routeSessionId, user, chat.busy, routeLoadAttempt]);

  useEffect(() => {
    const prompt = searchParams.get("q")?.trim();
    if (!prompt) return;
    autoSendStartedRef.current = false;
    const requestedModel = searchParams.get("model");
    if (requestedModel) setSelectedModel(requestedModel);
    setPendingAutoDraft(emptyDraft(prompt));
    const next = new URLSearchParams(searchParams);
    next.delete("q");
    next.delete("model");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (
      authLoading
      || chat.busy
      || !pendingAutoDraft.text
      || autoSendStartedRef.current
      || (Boolean(user) && webSearchEnabled && availabilityQuery.isFetching)
      || (routeSessionId && routeSessionState?.status !== "loaded")
    ) return;
    // Deferring avoids React StrictMode's development-only effect cleanup from
    // aborting the request before the second effect pass can own it.
    const timer = window.setTimeout(() => {
      if (autoSendStartedRef.current) return;
      autoSendStartedRef.current = true;
      const nextDraft = pendingAutoDraft;
      void send(nextDraft).finally(() => setPendingAutoDraft(emptyDraft()));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [
    authLoading,
    availabilityQuery.isFetching,
    chat.busy,
    pendingAutoDraft,
    routeSessionId,
    routeSessionState?.status,
    send,
    user,
    webSearchEnabled,
  ]);

  useEffect(() => {
    const onFocus = () => {
      if (!user || chat.busy) return;
      void refreshSessions();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [chat.busy, refreshSessions, user]);

  const newChat = () => {
    activeStreamSessionIdRef.current = null;
    chat.reset();
    setDraft(emptyDraft());
    onPaperSelectionChange?.(undefined);
    setWebSearchEnabled(false);
    setReasoningEffort("low");
    setLiveTitle("");
    if (mode === "paper") onReaderNewChat?.();
    else navigate("/chat");
  };
  const saveRename = async (id: string, title: string) => {
    try {
      const updated = await updateSession(id, { title });
      manualTitleLockRef.current.add(id);
      if (id === routeSessionId) setLiveTitle(updated.title);
      setSessions((previous) => previous.map((session) => session.id === id ? updated : session));
      return true;
    } catch (error) {
      setSessionError(error instanceof Error ? error.message : "Rename failed");
      return false;
    }
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
  const archive = useChatArchive({
    messages: chat.messages,
    refreshSessions,
    resetChat: chat.reset,
    restoreDraft: setDraft,
    clearTitle: () => setLiveTitle(""),
  });
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

  const changeReasoningEffort = async (effort: ReasoningEffort) => {
    const previousEffort = reasoningEffort;
    setReasoningEffort(effort);
    if (!routeSessionId) return;
    try {
      const updated = await updateSession(routeSessionId, {
        reasoning_effort: effort,
      });
      setSessions((previous) => previous.map((session) => (
        session.id === routeSessionId ? updated : session
      )));
    } catch (error) {
      setReasoningEffort(previousEffort);
      setSessionError(
        error instanceof Error ? error.message : "Effort change failed",
      );
    }
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
  const current = sessions.find((session) => session.id === routeSessionId);
  const isEmpty = chat.messages.length === 0;
  const routeStateMatches = routeSessionState?.id === routeSessionId;
  const isRouteSessionLoading = Boolean(routeSessionId && (
    authLoading || (user && (!routeStateMatches || routeSessionState?.status === "loading"))
  ));
  const routeSessionError = routeStateMatches && routeSessionState?.status === "error"
    ? routeSessionState.error
    : undefined;
  const openRouterFallbackEnabled = Boolean(
    openRouterCredentialQuery.data?.fallback_enabled,
  );
  const composerDraft = onPaperSelectionChange
    ? (paperSelection ? { ...draft, paperSelection } : { text: draft.text, paperMentions: draft.paperMentions })
    : draft;
  const composerProps = {
    onSend: send,
    busy: chat.busy,
    onStop: chat.stop,
    draft: composerDraft,
    onDraftChange: (next: ChatDraft) => {
      if (onPaperSelectionChange) {
        setDraft({ text: next.text, paperMentions: next.paperMentions });
        if (next.paperSelection !== paperSelection) onPaperSelectionChange(next.paperSelection);
      } else {
        setDraft(next);
      }
    },
    models,
    selectedModel,
    onModelChange: (model: string) => void changeModel(model),
    disabled: chatPaused || authLoading,
    describedBy: chatPaused ? "chat-paused-description" : undefined,
    paperMentionsEnabled: Boolean(availabilityQuery.data?.paper_mentions_enabled),
    paperSelectionEnabled: availabilityQuery.data?.paper_reader_selection_enabled === true,
    paperArtifactsEnabled: mode === "general" && availabilityQuery.data?.paper_artifacts_enabled === true,
    webSearchAvailable,
    webSearchEnabled,
    onWebSearchChange: setWebSearchEnabled,
    reasoningEffort,
    onReasoningEffortChange: (effort: ReasoningEffort) => void changeReasoningEffort(effort),
  };

  return (
    <GeneralArtifactProvider enabled={mode === "general"} workspaceKey={routeSessionId ?? "new-chat"} onAskAiFix={(prompt) => { void send(emptyDraft(prompt)); }}>
    <div className={`chat-page${mode === "paper" ? " chat-page--reader" : ""}`} style={{ height: mode === "paper" ? "100%" : `calc(100dvh - ${headerHeight}px)` }}>
      {mode === "general" && <ChatSessionNavigation
        sessions={sessions}
        activeSessionId={routeSessionId}
        loading={sessionsLoading}
        error={sessionError}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNew={newChat}
        onNavigate={(sessionId) => navigate(`/chat/${sessionId}`)}
        onRename={saveRename}
        onDelete={(sessionId) => void remove(sessionId)}
      />}

      <GeneralArtifactWorkspace enabled={mode === "general"}>
      <section className="chat-main" data-testid="active-chat-pane">
        <div className="chat-topbar">
          {mode === "general" && !sidebarOpen && <button type="button" className="icon-btn" onClick={() => setSidebarOpen(true)} title="Open sidebar"><PanelIcon /></button>}
          {mode === "paper" && <button type="button" className="chat-reader-action" onClick={newChat}>New chat</button>}
          <span className="chat-topbar-title">{isRouteSessionLoading
            ? current?.title || ""
            : liveTitle || current?.title || (isEmpty ? "" : "New chat")}</span>
          {staging && <span className="chat-staging-badge">Staging</span>}
          {mode === "paper" && <Link className="chat-reader-action" to="/chat">All chats</Link>}
          {mode === "general" && current?.primary_paper && (
            <Link
              className="chat-reader-action"
              to={`/pdf/${current.primary_paper.route_id}`}
              onClick={(event) => {
                if (!canNavigateAwayFromArtifact()) {
                  event.preventDefault();
                  return;
                }
                const readerRoute = current.primary_paper!.route_id;
                sessionStorage.setItem(`pwc:reader:session:${readerRoute}`, current.id);
                if (routeViewerPage) {
                  sessionStorage.setItem(`pwc:reader:page:${readerRoute}`, String(routeViewerPage));
                }
              }}
            >Open reader</Link>
          )}
          {routeSessionId && routeStateMatches && routeSessionState?.status === "loaded" && !isEmpty && (
            <ChatSharing
              sessionId={routeSessionId}
              busy={chat.busy}
              loading={isRouteSessionLoading}
              hasPaperSelection={chat.messages.some((message) => Boolean(message.paperSelection))}
              onError={setSessionError}
            />
          )}
        </div>

        {mode === "general" && latexPaper && <LatexPaperArtifact descriptor={latexPaper} />}
        {isRouteSessionLoading && !pendingAutoDraft.text ? <div className="chat-session-loading" role="status" aria-live="polite">
          <Spinner />
          <span>Loading conversation…</span>
        </div> : routeSessionError ? <div className="chat-session-load-error" role="alert">
          <p>{routeSessionError}</p>
          <button type="button" onClick={() => {
            setRouteSessionState({ id: routeSessionId!, status: "loading" });
            setRouteLoadAttempt((attempt) => attempt + 1);
          }}>Try again</button>
        </div> : isEmpty && !pendingAutoDraft.text ? <div className="chat-empty"><div className="chat-empty-inner">
          <div className="chat-empty-eyebrow">{mode === "paper" ? "Paper chat" : "Research chat"}</div>
          <h1 className="chat-empty-title">{mode === "paper" ? "Ask about this paper" : <>Ask <em>Papers With Code</em></>}</h1>
          <p className="chat-empty-sub">{mode === "paper" ? "Questions are grounded in the open paper. Add up to three other papers with @." : "Answers are grounded in a live hybrid search over papers, tasks, and benchmarks — with citations you can follow."}</p>
          {staging && <p className="chat-staging-access-note">
            This is a limited staging preview. Only approved Hugging Face users can start chats.
          </p>}
          <ChatComposerSurface
            variant="empty"
            composerProps={composerProps}
            provider={selectedProvider}
            paused={chatPaused}
            suggestions={mode === "paper" ? READER_PROMPTS : SUGGESTED_CHAT_PROMPTS}
          />
        </div></div> : <>
          {chat.sessionError && <div className="chat-session-error" role="alert">{chat.sessionError}</div>}
          <ChatConversation
            messages={chat.messages}
            papers={chat.papers}
            busy={chat.busy}
            queuedDraft={pendingAutoDraft.text ? pendingAutoDraft : undefined}
            paperMentionsEnabled={Boolean(availabilityQuery.data?.paper_mentions_enabled)}
            archivePending={archive.pending}
            openRouterFallbackEnabled={openRouterFallbackEnabled}
            onToggleBlock={chat.toggleBlock}
            onEditAndResend={chat.editAndResend}
            onArchiveOld={() => void archive.archiveOld()}
            onArchiveOldest={() => void archive.archiveOldest()}
          />
          <ChatComposerSurface
            variant="followup"
            composerProps={composerProps}
            provider={selectedProvider}
            paused={chatPaused}
          />
        </>}
      </section>
      </GeneralArtifactWorkspace>
      {chat.capacityRequest && (
        <ChatCapacityDialog
          retryAt={chat.capacityRequest.retryAt}
          onCancel={chat.cancelCapacity}
          onRetry={() => {
            if (chat.retryCapacity()) {
              setDraft(emptyDraft());
              onPaperSelectionChange?.(undefined);
            }
          }}
        />
      )}
      {chat.disabledRequest && <ChatDisabledDialog onClose={() => {
        const restored = chat.disabledRequest?.draft ?? draft;
        setDraft(restored);
        onPaperSelectionChange?.(restored.paperSelection);
        chat.dismissDisabled();
        void availabilityQuery.refetch();
      }} />}
    </div>
    </GeneralArtifactProvider>
  );
};

const ChatView: React.FC = () => <ChatExperience />;

export default ChatView;

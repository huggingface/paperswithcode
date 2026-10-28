import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreVertical, X } from "lucide-react";

import { useChatViewportHeight } from "@/hooks/useChatViewportHeight";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

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
import { DEFAULT_REASONING_EFFORT, isChatLive, type ChatDraft, type PaperSelectionDraft } from "@/lib/chat";
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
import { ApiError } from "@/lib/apiTransport";
import { isStagingEnvironment } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";
import {
  OPENROUTER_CREDENTIAL_QUERY_KEY,
  useOpenRouterCredential,
} from "@/lib/openrouter";
import {
  OPENAI_USAGE_QUERY_KEY,
  dismissOpenAICreditsNotice,
  openAiCreditsNotice,
  readDismissedOpenAICreditsNotice,
  useOpenAIUsage,
} from "@/lib/openaiCredits";
import {
  DEFAULT_CHAT_MODEL,
  PRODUCTION_FALLBACK_CHAT_MODELS,
  STAGING_FALLBACK_CHAT_MODELS,
  type ChatModelChoice,
  type ChatSession,
  type ChatSessionDetail,
  type LatexPaperArtifactDescriptor,
  getChatModels,
  getSession,
  isSponsoredChatModel,
  providerForChatModel,
  removeSession,
  toUiMessages,
  updateSession,
} from "@/lib/chatSessions";

import { chatSessionKeys, chatSessionListQuery, chatSessionQuery } from "@/lib/chatSessionQueries";

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
  onReaderClose?: () => void;
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

const ChatExperienceContent: React.FC<ChatExperienceProps> = ({
  mode = "general",
  routeSessionId: suppliedSessionId,
  primaryPaper,
  currentPage,
  paperSelection,
  onPaperSelectionChange,
  onSessionId: onReaderSessionId,
  onReaderSubmit,
  onReaderNewChat,
  onReaderClose,
}) => {
  const { sessionId: paramSessionId } = useParams<{ sessionId: string }>();
  const routeSessionId = suppliedSessionId ?? (mode === "general" ? paramSessionId : undefined);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, isLoading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  const userId = user?.hf_subject ?? null;
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
  const sessionsQuery = useQuery({ ...chatSessionListQuery(userId), enabled: Boolean(user) && !authLoading });
  const sessions = sessionsQuery.data ?? [];
  const [streamedArtifact, setStreamedArtifact] = useState<{ sessionId: string; descriptor: LatexPaperArtifactDescriptor } | null>(null);
  const [sessionError, setSessionError] = useState("");
  const setSessions = (update: (previous: ChatSession[]) => ChatSession[]) => {
    queryClient.setQueryData<ChatSession[]>(chatSessionKeys.list(userId), (previous) => update(previous ?? []));
  };
  const patchSession = (id: string, patch: Partial<ChatSessionDetail>) => {
    setSessions((previous) => previous.map((session) => session.id === id ? { ...session, ...patch } : session));
    queryClient.setQueryData<ChatSessionDetail>(chatSessionKeys.detail(userId, id), (previous) => (
      previous ? { ...previous, ...patch } : previous
    ));
  };
  const queuedLaunchRef = useRef(readQueuedChatLaunch());
  // Queued launch controls belong to the chat the launch returns to.
  const requestedModelRef = useRef(searchParams.get("model") || queuedLaunchRef.current?.model);
  const [models, setModels] = useState<ChatModelChoice[]>(
    staging ? STAGING_FALLBACK_CHAT_MODELS : PRODUCTION_FALLBACK_CHAT_MODELS,
  );
  const [selectedModel, setSelectedModel] = useState(
    requestedModelRef.current || DEFAULT_CHAT_MODEL,
  );
  const selectedProvider = providerForChatModel(models, selectedModel);
  const selectedSponsored = isSponsoredChatModel(models, selectedModel);
  const userBilledInference = selectedProvider === "huggingface" && !selectedSponsored;
  const openRouterCredentialQuery = useOpenRouterCredential(
    Boolean(user && selectedProvider === "openrouter"),
  );
  const openAiUsageQuery = useOpenAIUsage(
    isChatLive() && Boolean(user) && selectedProvider === "openai",
  );
  const [dismissedCreditsNotice, setDismissedCreditsNotice] = useState(
    () => readDismissedOpenAICreditsNotice(),
  );
  const creditsNotice = openAiCreditsNotice(
    openAiUsageQuery.data,
    selectedProvider,
    dismissedCreditsNotice,
  );
  const [draft, setDraft] = useState<ChatDraft>(() => emptyDraft());
  const reasoningEffort = DEFAULT_REASONING_EFFORT;
  // Web search has no user control: every turn uses it whenever the deployment offers it.
  const webSearchEnabled = Boolean(availabilityQuery.data?.web_search_available);
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
  const routeSessionIdRef = useRef(routeSessionId);
  routeSessionIdRef.current = routeSessionId;
  // Tracks whether the selected route has initialized its transcript and controls.
  // Persisted data belongs to queries; the active transcript belongs to useChat.
  const [initializedRoute, setInitializedRoute] = useState<string | null | undefined>(undefined);
  const refreshSessions = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: chatSessionKeys.list(userId) });
  }, [queryClient, userId]);
  const chat = useChat({
    sessionId: routeSessionId ?? null,
    initialModel: selectedModel,
    webSearchEnabled,
    reasoningEffort,
    primaryPaperRouteId: mode === "paper" ? primaryPaper?.routeId : undefined,
    viewerContext: mode === "paper" && currentPage
      ? () => ({ page: Math.max(1, Math.min(10_000, currentPage())) })
      : undefined,
    loadSession: async (id) => {
      const detail = await queryClient.fetchQuery(chatSessionQuery(userId, id));
      setStreamedArtifact((previous) => previous?.sessionId === id ? null : previous);
      return detail;
    },
    onSessionId: (id, originSessionId, configuration) => {
      void queryClient.cancelQueries({ queryKey: chatSessionKeys.list(userId) });
      const now = new Date().toISOString();
      setSessions((previous) => previous.some((session) => session.id === id)
        ? previous.map((session) => session.id === id ? { ...session, is_busy: true } : session)
        : [{
            id,
            title: "New chat",
            selected_model: configuration?.model ?? selectedModel,
            created_at: now,
            updated_at: now,
            message_count: 1,
            is_busy: true,
            web_search_enabled: configuration?.webSearchEnabled ?? webSearchEnabled,
            reasoning_effort: configuration?.reasoningEffort ?? reasoningEffort,
          }, ...previous]);
      if ((routeSessionIdRef.current ?? null) === originSessionId && id !== originSessionId) {
        if (mode === "paper") onReaderSessionId?.(id);
        else navigate(`/chat/${id}`, { replace: true });
      }
    },
    onTitle: (title, sessionId) => {
      if (sessionId && !manualTitleLockRef.current.has(sessionId)) patchSession(sessionId, { title });
    },
    onSettled: (sessionId) => {
      if (sessionId) patchSession(sessionId, { is_busy: false });
      void queryClient.invalidateQueries({ queryKey: OPENAI_USAGE_QUERY_KEY });
      void refreshSessions();
    },
    onProviderTerminal: () => {
      void queryClient.invalidateQueries({ queryKey: OPENROUTER_CREDENTIAL_QUERY_KEY });
    },
    onPaperArtifact: (event, sessionId) => {
      if (sessionId) setStreamedArtifact({ sessionId, descriptor: event.descriptor });
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
    window.location.href = hfLoginUrl(returnTo, userBilledInference);
  }, [mode, primaryPaper, reasoningEffort, selectedModel, userBilledInference]);

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
    if (userBilledInference && !inferenceConnectedRef.current) {
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
    sessionStorage.removeItem(CHAT_AUTO_SEND_KEY);
    if (!sendChat(payload)) {
      restoreAuthorizationPrompt(
        payload,
        "Your prompt was not sent. It is ready to retry.",
      );
      return;
    }
    sessionStorage.removeItem(CHAT_DRAFT_KEY);
    sessionStorage.removeItem(CHAT_MODEL_KEY);
    sessionStorage.removeItem(CHAT_AUTH_ATTEMPTED_KEY);
    clearQueuedChatLaunch();
    queuedLaunchRef.current = null;
    setDraft(emptyDraft());
    onPaperSelectionChange?.(undefined);
    if (mode === "paper") onReaderSubmit?.();
  }, [authorizeInference, mode, onPaperSelectionChange, onReaderSubmit, paperSelection, restoreAuthorizationPrompt, sendChat, user, userBilledInference]);

  useEffect(() => {
    if (authLoading || !user) return;
    const savedModel = sessionStorage.getItem(CHAT_MODEL_KEY);
    if (savedModel) setSelectedModel(savedModel);
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

  const selectedTurn = chat.selectedBusy;
  const { load: loadChat, activeConfiguration } = chat;
  const routeQuery = useQuery({
    ...chatSessionQuery(userId, routeSessionId ?? null),
    enabled: Boolean(routeSessionId && user && !authLoading && !selectedTurn),
    // Navigating back to a saved conversation refreshes it. Focus refreshes only
    // the sidebar, so a transcript being edited does not get replaced.
    refetchOnMount: "always",
  });
  // Only the owner can open /chat/:id. Anyone else who was handed that URL
  // lands on its public share when the owner created one.
  const routeNotOwned = !authLoading && (
    !user || (routeQuery.error instanceof ApiError && routeQuery.error.status === 404)
  );
  const publicShareQuery = useQuery({
    queryKey: ["chatSessionPublicShare", routeSessionId],
    queryFn: () => chatApi.getSessionPublicShare(routeSessionId ?? ""),
    enabled: mode === "general" && Boolean(routeSessionId) && routeNotOwned,
    retry: false,
  });
  const publicSharePath = publicShareQuery.data?.public_path;
  useEffect(() => {
    if (publicSharePath) navigate(publicSharePath, { replace: true });
  }, [navigate, publicSharePath]);
  const detail = routeQuery.data;
  // A newly admitted turn already initialized the visible transcript, even when
  // its first canonical fetch is still pending after streaming finishes.
  const routeReady = selectedTurn || initializedRoute === (routeSessionId ?? null);
  const latexPaper = streamedArtifact && streamedArtifact.sessionId === routeSessionId
    ? streamedArtifact.descriptor
    : detail?.latex_paper;
  const routeViewerPage = [...(detail?.messages ?? [])].reverse()
    .find((message) => message.role === "user" && message.viewer_context)?.viewer_context?.page;

  useLayoutEffect(() => {
    const selectedId = routeSessionId ?? null;
    if (initializedRoute === selectedId) return;
    if (selectedTurn) {
      setInitializedRoute(selectedId);
      const configuration = activeConfiguration;
      if (configuration) {
        if (configuration.model) setSelectedModel(configuration.model);
      }
      return;
    }
    if (!selectedId) {
      loadChat([], null);
      setInitializedRoute(null);
      return;
    }
    if (!detail || routeQuery.isFetching) return;
    setInitializedRoute(selectedId);
    loadChat(toUiMessages(detail), selectedId, detail.is_busy, {
      model: detail.selected_model,
      webSearchEnabled: detail.web_search_enabled,
      reasoningEffort: detail.reasoning_effort ?? "high",
    });
    setSessionError("");
    setSelectedModel(detail.selected_model);
  }, [routeSessionId, selectedTurn, detail, loadChat, activeConfiguration, routeQuery.isFetching, initializedRoute]);

  useEffect(() => {
    if (authLoading) return;
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
  }, [authLoading, searchParams, setSearchParams]);

  useEffect(() => {
    if (
      authLoading
      || chat.busy
      || !pendingAutoDraft.text
      || autoSendStartedRef.current
      || (Boolean(user) && availabilityQuery.isFetching)
      || (routeSessionId && !routeReady)
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
    routeReady,
    send,
    user,
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
    if (window.innerWidth <= 900) setSidebarOpen(false);
    loadChat([], null);
    setInitializedRoute(null);
    setDraft(emptyDraft());
    onPaperSelectionChange?.(undefined);
    if (mode === "paper") onReaderNewChat?.();
    else navigate("/chat");
  };
  const saveRename = async (id: string, title: string) => {
    try {
      const updated = await updateSession(id, { title });
      manualTitleLockRef.current.add(id);
      patchSession(id, updated);
      return true;
    } catch (error) {
      setSessionError(error instanceof Error ? error.message : "Rename failed");
      return false;
    }
  };
  const remove = async (id: string) => {
    const active = chat.busy && id === chat.activeSessionId;
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
  });
  const changeModel = async (model: string) => {
    const previousModel = selectedModel;
    setSelectedModel(model);
    if (!routeSessionId) return true;
    try {
      const updated = await updateSession(routeSessionId, { selected_model: model });
      patchSession(routeSessionId, { selected_model: updated.selected_model });
      setSessionError("");
      return true;
    }
    catch (error) {
      setSelectedModel(previousModel);
      setSessionError(error instanceof Error ? error.message : "Model change failed");
      return false;
    }
  };
  const lunaAvailable = models.some((model) => model.id === DEFAULT_CHAT_MODEL);
  const retryWithLuna = async () => {
    if (await changeModel(DEFAULT_CHAT_MODEL)) chat.retryLatest();
  };

  const viewportHeight = useChatViewportHeight(mode === "general");
  const visibleSessions = sessions.map((session) => session.id === chat.activeSessionId && chat.busy
    ? { ...session, is_busy: true, title: manualTitleLockRef.current.has(session.id) ? session.title : chat.activeTitle || session.title }
    : session);
  const current = visibleSessions.find((session) => session.id === routeSessionId);
  // The sidebar loads only recent chats, so older reader chats need the detail.
  const sessionPrimaryPaper = current?.primary_paper ?? detail?.primary_paper;
  const isEmpty = chat.messages.length === 0;
  const isRouteSessionLoading = Boolean(routeSessionId && (
    authLoading || (user && !routeReady && !routeQuery.isError)
    || publicShareQuery.isFetching || publicSharePath
  ));
  const routeSessionError = !routeReady && !isRouteSessionLoading && routeQuery.error?.message;
  const openRouterFallbackEnabled = Boolean(
    openRouterCredentialQuery.data?.fallback_enabled,
  );
  const composerDraft = onPaperSelectionChange
    ? (paperSelection ? { ...draft, paperSelection } : { text: draft.text, paperMentions: draft.paperMentions })
    : draft;
  const composerProps = {
    onSend: send,
    busy: selectedTurn,
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
    disabled: chatPaused || authLoading || (chat.busy && !selectedTurn),
    describedBy: chatPaused ? "chat-paused-description" : undefined,
    paperMentionsEnabled: Boolean(availabilityQuery.data?.paper_mentions_enabled),
    paperSelectionEnabled: availabilityQuery.data?.paper_reader_selection_enabled === true,
    paperArtifactsEnabled: mode === "general" && availabilityQuery.data?.paper_artifacts_enabled === true,
  };

  return (
    <GeneralArtifactProvider enabled={mode === "general"} workspaceKey={routeSessionId ?? "new-chat"} onAskAiFix={(prompt) => { void send(emptyDraft(prompt)); }}>
    <div className={`chat-page${mode === "paper" ? " chat-page--reader" : ""}`} style={{ height: viewportHeight }}>
      {mode === "general" && <ChatSessionNavigation
        sessions={visibleSessions}
        activeSessionId={routeSessionId}
        loading={sessionsQuery.isLoading}
        error={sessionError || sessionsQuery.error?.message || ""}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNew={newChat}
        onNavigate={(sessionId) => {
          if (window.innerWidth <= 900) setSidebarOpen(false);
          navigate(`/chat/${sessionId}`);
        }}
        onRename={saveRename}
        onDelete={(sessionId) => void remove(sessionId)}
      />}

      <GeneralArtifactWorkspace enabled={mode === "general"}>
      <section className="chat-main" data-testid="active-chat-pane">
        <div className="chat-topbar">
          {mode === "general" && !sidebarOpen && <button type="button" className="icon-btn" onClick={() => setSidebarOpen(true)} title="Open sidebar"><PanelIcon /></button>}
          <span className="chat-topbar-title">{isRouteSessionLoading
            ? current?.title || ""
            : current?.title || detail?.title || (isEmpty ? "" : "New chat")}</span>
          {staging && <span className="chat-staging-badge">Staging</span>}
          {mode === "general" && routeSessionId && sessionPrimaryPaper && (
            <Link
              className="chat-reader-action"
              to={`/pdf/${sessionPrimaryPaper.route_id}`}
              onClick={(event) => {
                if (!canNavigateAwayFromArtifact()) {
                  event.preventDefault();
                  return;
                }
                const readerRoute = sessionPrimaryPaper.route_id;
                sessionStorage.setItem(`pwc:reader:session:${readerRoute}`, routeSessionId);
                if (routeViewerPage) {
                  sessionStorage.setItem(`pwc:reader:page:${readerRoute}`, String(routeViewerPage));
                }
              }}
            >Open reader</Link>
          )}
          {routeSessionId && routeReady && !isEmpty && (
            <ChatSharing
              sessionId={routeSessionId}
              busy={selectedTurn}
              loading={isRouteSessionLoading}
              hasPaperSelection={chat.messages.some((message) => Boolean(message.paperSelection))}
              onError={setSessionError}
            />
          )}
          {mode === "paper" && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button type="button" className="icon-btn chat-reader-icon-btn" aria-label="Chat options" title="Chat options">
                  <MoreVertical aria-hidden="true" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={newChat}>New chat</DropdownMenuItem>
                <DropdownMenuItem asChild><Link to="/chat">All chats</Link></DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          {mode === "paper" && onReaderClose && (
            <button type="button" className="icon-btn chat-reader-icon-btn" onClick={onReaderClose} aria-label="Close chat" title="Close chat">
              <X aria-hidden="true" />
            </button>
          )}
        </div>

        {creditsNotice && (
          <div className="chat-credits-notice" role="status">
            <span>{creditsNotice.message}</span>
            <button
              type="button"
              className="chat-credits-notice-close"
              aria-label="Dismiss credits notice"
              onClick={() => {
                dismissOpenAICreditsNotice(creditsNotice.resetsAt);
                setDismissedCreditsNotice(creditsNotice.resetsAt);
              }}
            >
              ×
            </button>
          </div>
        )}

        {mode === "general" && latexPaper && <LatexPaperArtifact descriptor={latexPaper} />}
        {isRouteSessionLoading && !pendingAutoDraft.text ? <div className="chat-session-loading" role="status" aria-live="polite">
          <Spinner />
          <span>Loading conversation…</span>
        </div> : routeSessionError ? <div className="chat-session-load-error" role="alert">
          <p>{routeSessionError}</p>
          <button type="button" onClick={() => {
            void routeQuery.refetch();
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
            sponsored={selectedSponsored}
            paused={chatPaused}
            error={chat.sessionError}
            suggestions={mode === "paper" ? READER_PROMPTS : SUGGESTED_CHAT_PROMPTS}
          />
        </div></div> : <>
          <ChatConversation
            messages={chat.messages}
            papers={chat.papers}
            busy={selectedTurn}
            queuedDraft={pendingAutoDraft.text ? pendingAutoDraft : undefined}
            paperMentionsEnabled={Boolean(availabilityQuery.data?.paper_mentions_enabled)}
            archivePending={archive.pending}
            openRouterFallbackEnabled={openRouterFallbackEnabled}
            onToggleBlock={chat.toggleBlock}
            onEditAndResend={chat.editAndResend}
            onRetryFromProgress={chat.retryFromProgress}
            onRetryWithLuna={lunaAvailable ? () => void retryWithLuna() : undefined}
            onArchiveOld={() => void archive.archiveOld()}
            onArchiveOldest={() => void archive.archiveOldest()}
          />
          <ChatComposerSurface
            variant="followup"
            composerProps={composerProps}
            provider={selectedProvider}
            sponsored={selectedSponsored}
            paused={chatPaused}
            error={chat.sessionError}
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

// Authentication changes end the browser's ownership of any private turn and
// editable route state. Queries are independently scoped to that same account.
export const ChatExperience: React.FC<ChatExperienceProps> = (props) => {
  const { user } = useAuth();
  return <ChatExperienceContent key={user?.hf_subject ?? "guest"} {...props} />;
};

const ChatView: React.FC = () => <ChatExperience />;

export default ChatView;

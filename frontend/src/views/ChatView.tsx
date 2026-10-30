import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { useChatViewportHeight } from "@/hooks/useChatViewportHeight";

import { ChatComposerSurface } from "@/components/chat/ChatComposerSurface";
import { ChatConversation } from "@/components/chat/ChatConversation";
import {
  ChatCapacityDialog,
  ChatDisabledDialog,
} from "@/components/chat/ChatDialogs";
import { ChatSessionNavigation } from "@/components/chat/ChatSessionNavigation";
import { ChatSharing } from "@/components/chat/ChatSharing";
import {
  ChatEmptyState,
  GeneralArtifactProvider,
  GeneralArtifactWorkspace,
  OpenAICreditsNotice,
  OpenReaderLink,
  ReaderChatMenu,
} from "@/components/chat/ChatPageChrome";
import { LatexPaperArtifact } from "@/components/chat/LatexPaperArtifact";
import { useChatArchive } from "@/components/chat/useChatArchive";
import { useChatAutoSend } from "@/components/chat/useChatAutoSend";
import { usePublicShareRedirect } from "@/components/chat/usePublicShareRedirect";
import { useChatModelSelection } from "@/components/chat/useChatModelSelection";
import { useChatSessionActions, useChatSessionCache } from "@/components/chat/useChatSessionActions";
import { useInferenceAuthorization } from "@/components/chat/useInferenceAuthorization";
import { PanelIcon, Spinner } from "@/components/chat/icons";
import { useChat } from "@/hooks/useChat";
import { DEFAULT_REASONING_EFFORT, isChatLive, type ChatDraft, type PaperSelectionDraft } from "@/lib/chat";
import {
  clearQueuedChatLaunch,
  readQueuedChatLaunch,
  stopChatAutoSend,
} from "@/lib/chatLaunch";
import { READER_CHAT_PROMPTS, SUGGESTED_CHAT_PROMPTS } from "@/lib/chatPrompts";
import { emptyChatDraft } from "@/lib/paperSelection";
import { ApiError } from "@/lib/apiTransport";
import { isStagingEnvironment } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";
import {
  OPENROUTER_CREDENTIAL_QUERY_KEY,
  useOpenRouterCredential,
} from "@/lib/openrouter";
import { OPENAI_USAGE_QUERY_KEY } from "@/lib/openaiCredits";
import {
  DEFAULT_CHAT_MODEL,
  type LatexPaperArtifactDescriptor,
  toUiMessages,
} from "@/lib/chatSessions";

import { chatAvailabilityQuery, chatSessionListQuery, chatSessionQuery } from "@/lib/chatSessionQueries";


/** In the reader, the PDF owns the selection: the composer draft carries only text and mentions. */
const withReaderSelection = (
  draft: ChatDraft,
  readerOwnsSelection: boolean,
  paperSelection: PaperSelectionDraft | undefined,
): ChatDraft => {
  if (!readerOwnsSelection) return draft;
  return paperSelection
    ? { ...draft, paperSelection }
    : { text: draft.text, paperMentions: draft.paperMentions };
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
  const [searchParams] = useSearchParams();
  const { user, isLoading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  const userId = user?.hf_subject ?? null;
  const staging = isStagingEnvironment();
  const availabilityQuery = useQuery({
    ...chatAvailabilityQuery(),
    enabled: isChatLive() && Boolean(user),
  });
  const availability = availabilityQuery.data;
  const chatPaused = availability?.status === "paused"
    || (mode === "paper" && availability?.paper_reader_chat_enabled === false);
  const sessionsQuery = useQuery({ ...chatSessionListQuery(userId), enabled: Boolean(user) && !authLoading });
  const sessions = sessionsQuery.data ?? [];
  const { markSessionBusy, patchSession, refreshSessions } = useChatSessionCache(userId);
  const [streamedArtifact, setStreamedArtifact] = useState<{ sessionId: string; descriptor: LatexPaperArtifactDescriptor } | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [queuedLaunch] = useState(readQueuedChatLaunch);
  const routeSessionIdRef = useRef(routeSessionId);
  routeSessionIdRef.current = routeSessionId;
  // Queued launch controls belong to the chat the launch returns to.
  const model = useChatModelSelection({
    userId,
    signedIn: Boolean(user),
    authLoading,
    requestedModel: searchParams.get("model") || queuedLaunch?.model,
    routeSessionIdRef,
  });
  const { selectedModel, setSelectedModel } = model;
  const openRouterCredentialQuery = useOpenRouterCredential(
    Boolean(user && model.provider === "openrouter"),
  );
  const [draft, setDraft] = useState<ChatDraft>(() => emptyChatDraft());
  const reasoningEffort = DEFAULT_REASONING_EFFORT;
  // Web search has no user control: every turn uses it whenever the deployment offers it.
  const webSearchEnabled = Boolean(availability?.web_search_available);
  const [pendingAutoDraft, setPendingAutoDraft] = useState<ChatDraft>(() => {
    const queryPrompt = searchParams.get("q")?.trim();
    if (queryPrompt) return emptyChatDraft(queryPrompt);
    return queuedLaunch?.draft ?? emptyChatDraft();
  });
  const [sidebarOpen, setSidebarOpen] = useState(() => typeof window === "undefined" || window.innerWidth > 900);
  const manualTitleLockRef = useRef<Set<string>>(new Set());
  // Tracks whether the selected route has initialized its transcript and controls.
  // Persisted data belongs to queries; the active transcript belongs to useChat.
  const [initializedRoute, setInitializedRoute] = useState<string | null | undefined>(undefined);
  const showDraft = useCallback((nextDraft: ChatDraft) => {
    setDraft(nextDraft);
    onPaperSelectionChange?.(nextDraft.paperSelection);
  }, [onPaperSelectionChange]);
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
      markSessionBusy(id, {
        model: configuration?.model ?? selectedModel,
        webSearchEnabled: configuration?.webSearchEnabled ?? webSearchEnabled,
        reasoningEffort: configuration?.reasoningEffort ?? reasoningEffort,
      });
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
    onInterrupted: showDraft,
  });
  const sendChat = chat.send;

  useEffect(() => {
    if (chat.capacityRequest) showDraft(chat.capacityRequest.draft);
  }, [chat.capacityRequest, showDraft]);

  const authorizationReturnPath = useCallback(() => (
    mode === "paper" && primaryPaper
      ? `/pdf/${primaryPaper.routeId}`
      : routeSessionIdRef.current
        ? `/chat/${routeSessionIdRef.current}`
        : "/chat"
  ), [mode, primaryPaper]);
  const restoreUnsentPrompt = useCallback((nextDraft: ChatDraft, message: string) => {
    setPendingAutoDraft(emptyChatDraft());
    showDraft(nextDraft);
    setSessionError(message);
  }, [showDraft]);
  const authorization = useInferenceAuthorization({
    returnTo: authorizationReturnPath,
    selectedModel,
    reasoningEffort,
    userBilledInference: model.userBilledInference,
    onPromptRestored: restoreUnsentPrompt,
  });
  const { authorizeSend, restorePrompt } = authorization;

  const readerOwnsSelection = Boolean(onPaperSelectionChange);
  const send = useCallback(async (nextDraft: ChatDraft) => {
    const payload = withReaderSelection(nextDraft, readerOwnsSelection, paperSelection);
    const authorized = authorizeSend(payload, Boolean(user));
    if (authorized !== true && !(await authorized)) return;
    stopChatAutoSend();
    if (!sendChat(payload)) {
      restorePrompt(payload, "Your prompt was not sent. It is ready to retry.");
      return;
    }
    clearQueuedChatLaunch();
    setDraft(emptyChatDraft());
    onPaperSelectionChange?.(undefined);
    if (mode === "paper") onReaderSubmit?.();
  }, [authorizeSend, mode, onPaperSelectionChange, onReaderSubmit, paperSelection, readerOwnsSelection, restorePrompt, sendChat, user]);

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
  const publicShare = usePublicShareRedirect(
    mode === "general" ? routeSessionId : undefined,
    !authLoading && (!user || (routeQuery.error instanceof ApiError && routeQuery.error.status === 404)),
  );
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
      if (activeConfiguration?.model) setSelectedModel(activeConfiguration.model);
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
  }, [routeSessionId, selectedTurn, detail, loadChat, activeConfiguration, routeQuery.isFetching, initializedRoute, setSelectedModel]);

  useChatAutoSend({
    pendingDraft: pendingAutoDraft,
    setPendingDraft: setPendingAutoDraft,
    blocked: authLoading
      || chat.busy
      || (Boolean(user) && availabilityQuery.isFetching)
      || Boolean(routeSessionId && !routeReady),
    authLoading,
    signedIn: Boolean(user),
    send,
    restoreDraft: setDraft,
    setSelectedModel,
    onPaperSelectionChange,
  });

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
    setDraft(emptyChatDraft());
    onPaperSelectionChange?.(undefined);
    if (mode === "paper") onReaderNewChat?.();
    else navigate("/chat");
  };
  const sessionActions = useChatSessionActions({
    routeSessionId,
    selectedModel,
    setSelectedModel,
    patchSession,
    onRenamed: (id) => manualTitleLockRef.current.add(id),
    refreshSessions,
    onError: setSessionError,
    onSelectedDeleted: newChat,
    isActive: (id) => chat.busy && id === chat.activeSessionId,
    stopActive: chat.stop,
  });
  const archive = useChatArchive({
    messages: chat.messages,
    refreshSessions,
    resetChat: chat.reset,
    restoreDraft: setDraft,
  });
  const retryWithLuna = async () => {
    if (await sessionActions.changeModel(DEFAULT_CHAT_MODEL)) chat.retryLatest();
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
    || publicShare.pending
  ));
  const routeSessionError = !routeReady && !isRouteSessionLoading && routeQuery.error?.message;
  const composerProps = {
    onSend: send,
    busy: selectedTurn,
    onStop: chat.stop,
    draft: withReaderSelection(draft, readerOwnsSelection, paperSelection),
    onDraftChange: (next: ChatDraft) => {
      if (onPaperSelectionChange) {
        setDraft({ text: next.text, paperMentions: next.paperMentions });
        if (next.paperSelection !== paperSelection) onPaperSelectionChange(next.paperSelection);
      } else {
        setDraft(next);
      }
    },
    disabled: chatPaused || authLoading || (chat.busy && !selectedTurn),
    describedBy: chatPaused ? "chat-paused-description" : undefined,
    paperMentionsEnabled: Boolean(availability?.paper_mentions_enabled),
    paperSelectionEnabled: availability?.paper_reader_selection_enabled === true,
    paperArtifactsEnabled: mode === "general" && availability?.paper_artifacts_enabled === true,
  };
  const surfaceProps = {
    composerProps,
    provider: model.provider,
    sponsored: model.sponsored,
    paused: chatPaused,
    error: chat.sessionError,
  };

  return (
    <GeneralArtifactProvider enabled={mode === "general"} workspaceKey={routeSessionId ?? "new-chat"} onAskAiFix={(prompt) => { void send(emptyChatDraft(prompt)); }}>
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
        onRename={sessionActions.rename}
        onDelete={(sessionId) => void sessionActions.remove(sessionId)}
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
            <OpenReaderLink routeId={sessionPrimaryPaper.route_id} sessionId={routeSessionId} page={routeViewerPage} />
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
          {mode === "paper" && <ReaderChatMenu onNewChat={newChat} onClose={onReaderClose} />}
        </div>

        <OpenAICreditsNotice
          provider={model.provider}
          enabled={isChatLive() && Boolean(user) && model.provider === "openai"}
        />

        {mode === "general" && latexPaper && <LatexPaperArtifact descriptor={latexPaper} />}
        {isRouteSessionLoading && !pendingAutoDraft.text ? <div className="chat-session-loading" role="status" aria-live="polite">
          <Spinner />
          <span>Loading conversation…</span>
        </div> : routeSessionError ? <div className="chat-session-load-error" role="alert">
          <p>{routeSessionError}</p>
          <button type="button" onClick={() => {
            void routeQuery.refetch();
          }}>Try again</button>
        </div> : isEmpty && !pendingAutoDraft.text ? <ChatEmptyState mode={mode} staging={staging}>
          <ChatComposerSurface
            variant="empty"
            {...surfaceProps}
            suggestions={mode === "paper" ? READER_CHAT_PROMPTS : SUGGESTED_CHAT_PROMPTS}
          />
        </ChatEmptyState> : <>
          <ChatConversation
            messages={chat.messages}
            papers={chat.papers}
            busy={selectedTurn}
            queuedDraft={pendingAutoDraft.text ? pendingAutoDraft : undefined}
            paperMentionsEnabled={Boolean(availability?.paper_mentions_enabled)}
            archivePending={archive.pending}
            openRouterFallbackEnabled={Boolean(openRouterCredentialQuery.data?.fallback_enabled)}
            onToggleBlock={chat.toggleBlock}
            onEditAndResend={chat.editAndResend}
            onRetryFromProgress={chat.retryFromProgress}
            onRetryWithLuna={model.lunaAvailable ? () => void retryWithLuna() : undefined}
            onArchiveOld={() => void archive.archiveOld()}
            onArchiveOldest={() => void archive.archiveOldest()}
          />
          <ChatComposerSurface variant="followup" {...surfaceProps} />
        </>}
      </section>
      </GeneralArtifactWorkspace>
      {chat.capacityRequest && (
        <ChatCapacityDialog
          retryAt={chat.capacityRequest.retryAt}
          onCancel={chat.cancelCapacity}
          onRetry={() => {
            if (chat.retryCapacity()) {
              setDraft(emptyChatDraft());
              onPaperSelectionChange?.(undefined);
            }
          }}
        />
      )}
      {chat.disabledRequest && <ChatDisabledDialog onClose={() => {
        showDraft(chat.disabledRequest?.draft ?? draft);
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

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import {
  type ChatDraft,
  type ChatEvent,
  type ChatMessage,
  type ChatPaperHit,
  type ChatStreamRequest,
  ChatStreamError,
  ChatTransportError,
  isChatLive,
  isChatSmoothStreamingEnabled,
  resumeChat,
  streamChat,
} from "@/lib/chat";
import { emptyChatDraft, toPaperSelectionWire } from "@/lib/paperSelection";
import {
  ChatLatencyTracker,
  type ChatTerminalClassification,
} from "@/lib/chatLatency";
import {
  type ChatLifecycleAction,
  chatLifecycleReducer,
  initialChatLifecycle,
} from "@/lib/chatLifecycle";
import {
  createSmoothedChatStream,
  type SmoothedChatStream,
} from "@/lib/chatStreamSmoother";
import { cancelSession, getSession, toUiMessages } from "@/lib/chatSessions";

const WORKSPACE_STATUS_DELAY_MS = 750;
const STREAM_RECONNECT_DELAYS_MS = [250, 500, 1_000] as const;

const waitForReconnect = (delayMs: number, signal: AbortSignal): Promise<void> => (
  new Promise((resolve) => {
    const finish = () => {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", finish);
      resolve();
    };
    const timer = window.setTimeout(finish, delayMs);
    signal.addEventListener("abort", finish, { once: true });
  })
);

async function* reconnectChatStream(
  initialSource: AsyncGenerator<ChatEvent>,
  options: {
    signal: AbortSignal;
    getSessionId: () => string | null;
    getAfterSequence: () => number;
    onSequence: (sequence: number) => void;
    onDisconnect: () => void;
  },
): AsyncGenerator<ChatEvent> {
  let source = initialSource;
  let reconnectAttempts = 0;
  for (;;) {
    let sawTerminalEvent = false;
    try {
      for await (const event of source) {
        if (event.type === "done" || event.type === "error") sawTerminalEvent = true;
        yield event;
      }
      if (sawTerminalEvent || options.signal.aborted) return;
      throw new ChatTransportError();
    } catch (error) {
      options.onDisconnect();
      const sessionId = options.getSessionId();
      if (
        options.signal.aborted
        || sawTerminalEvent
        || !(error instanceof ChatTransportError)
        || !sessionId
        || reconnectAttempts >= STREAM_RECONNECT_DELAYS_MS.length
      ) throw error;
      await waitForReconnect(
        STREAM_RECONNECT_DELAYS_MS[reconnectAttempts],
        options.signal,
      );
      if (options.signal.aborted) return;
      reconnectAttempts += 1;
      source = resumeChat(sessionId, {
        signal: options.signal,
        afterSequence: options.getAfterSequence(),
        onSequence: options.onSequence,
      });
    }
  }
}

function findLastMatchingIndex<T>(items: T[], predicate: (item: T) => boolean): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (predicate(items[index])) return index;
  }
  return -1;
}

function useStableCallback<Args extends unknown[], Result>(
  callback: (...args: Args) => Result,
): (...args: Args) => Result {
  const callbackRef = useRef(callback);
  useLayoutEffect(() => {
    callbackRef.current = callback;
  });
  return useCallback((...args: Args) => callbackRef.current(...args), []);
}

interface UseChatOptions {
  sessionId: string | null;
  initialModel?: string;
  webSearchEnabled?: boolean;
  reasoningEffort?: "low" | "high" | "max";
  onSessionId: (id: string) => void;
  onTitle: (title: string) => void;
  onSettled: (sessionId: string | null) => void;
  onProviderTerminal?: () => void;
  onPaperArtifact?: (event: Extract<ChatEvent, { type: "paper_artifact" }>) => void;
  onInterrupted: (draft: ChatDraft) => void;
  primaryPaperRouteId?: string;
  viewerContext?: () => { page: number } | undefined;
}

interface EditRequest {
  targetId: string;
  snapshot: ChatMessage[];
}

interface PendingGeneration {
  question: string;
  draft: ChatDraft;
  request: ChatStreamRequest;
  optimistic: ChatMessage[];
  original: ChatMessage[];
  edit?: EditRequest;
  retryAt: number;
  retryAfterSeconds: number;
}

export function useChat(options: UseChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [sessionError, setSessionError] = useState("");
  const busyRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const smoothedStreamRef = useRef<{
    controller: AbortController;
    stream: SmoothedChatStream;
  } | null>(null);
  const presentationFrameRef = useRef<number | null>(null);
  const presentationTimerRef = useRef<number | null>(null);
  const presentationDirtyRef = useRef(false);
  const stoppedProjectionRef = useRef<{
    sessionId: string;
    messages: ChatMessage[];
  } | null>(null);
  const preparingTimerRef = useRef<number | null>(null);
  const workspaceStatusStateRef = useRef<"armed" | "shown" | "cleared">("cleared");
  const latencyRef = useRef<{
    controller: AbortController;
    tracker: ChatLatencyTracker;
  } | null>(null);
  const pendingCapacityRef = useRef<PendingGeneration | null>(null);
  const [capacityRequest, setCapacityRequest] = useState<Pick<
    PendingGeneration,
    "question" | "draft" | "retryAt" | "retryAfterSeconds"
  > | null>(null);
  const [disabledRequest, setDisabledRequest] = useState<{ question: string; draft: ChatDraft } | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  const lifecycleRef = useRef(initialChatLifecycle());
  const activeMessagesRef = useRef<ChatMessage[] | null>(null);
  const activeMessagesGenerationRef = useRef<number | null>(null);
  const activeProjectionVisibleRef = useRef(false);
  const optionsRef = useRef(options);
  const promptRef = useRef<ChatDraft>(emptyChatDraft());
  const idRef = useRef(0);
  const messagesGenerationRef = useRef(0);
  const activeSessionIdRef = useRef(options.sessionId);
  const renderedSessionIdRef = useRef(options.sessionId);
  if (renderedSessionIdRef.current !== options.sessionId) {
    renderedSessionIdRef.current = options.sessionId;
    if (activeSessionIdRef.current !== options.sessionId) {
      messagesGenerationRef.current += 1;
      latencyRef.current = null;
    }
  }
  optionsRef.current = options;
  messagesRef.current = messages;

  useEffect(() => () => {
    if (preparingTimerRef.current !== null) {
      window.clearTimeout(preparingTimerRef.current);
    }
    abortRef.current?.abort();
    smoothedStreamRef.current = null;
    if (presentationFrameRef.current !== null) cancelAnimationFrame(presentationFrameRef.current);
    if (presentationTimerRef.current !== null) window.clearTimeout(presentationTimerRef.current);
    pendingCapacityRef.current = null;
  }, []);
  useEffect(() => {
    if (!busyRef.current) activeSessionIdRef.current = options.sessionId;
  }, [options.sessionId]);
  useEffect(() => {
    const visibleMessages = (
      busyRef.current
      && options.sessionId === activeSessionIdRef.current
      ? activeMessagesRef.current
      : null
    );
    activeProjectionVisibleRef.current = visibleMessages !== null;
    if (visibleMessages) {
      setMessages(visibleMessages);
      messagesRef.current = visibleMessages;
    }
  }, [options.sessionId]);

  const papers = useMemo(() => {
    const map: Record<string, ChatPaperHit> = {};
    for (const message of messages) {
      for (const block of message.blocks ?? []) {
        if (block.kind === "tool") {
          for (const result of block.results ?? []) map[result.route_id] = result;
        }
      }
    }
    return map;
  }, [messages]);

  const nextId = () => `m${++idRef.current}_${Date.now().toString(36)}`;
  const transitionLifecycle = (
    action: ChatLifecycleAction,
    projectToVisible = true,
  ) => {
    const previous = {
      ...lifecycleRef.current,
      messages: activeMessagesRef.current ?? messagesRef.current,
      sessionId: activeSessionIdRef.current,
    };
    const next = chatLifecycleReducer(previous, action);
    lifecycleRef.current = next;
    if (activeMessagesRef.current) activeMessagesRef.current = next.messages;
    const announcedSessionId = action.type === "event"
      && action.event.type === "stream_start"
      ? action.event.session_id
      : null;
    if (announcedSessionId) {
      activeSessionIdRef.current = announcedSessionId;
      optionsRef.current.onSessionId(announcedSessionId);
    } else if (next.sessionId && next.sessionId !== previous.sessionId) {
      activeSessionIdRef.current = next.sessionId;
      optionsRef.current.onSessionId(next.sessionId);
    }
    if (next.title !== previous.title) optionsRef.current.onTitle(next.title);
    if (projectToVisible) {
      messagesRef.current = next.messages;
      setMessages(next.messages);
    }
    return next;
  };

  const projectsActiveStream = () => (
    activeMessagesGenerationRef.current === messagesGenerationRef.current
    || activeProjectionVisibleRef.current
  );

  const cancelPresentationFrame = () => {
    if (presentationFrameRef.current !== null) {
      cancelAnimationFrame(presentationFrameRef.current);
      presentationFrameRef.current = null;
    }
    if (presentationTimerRef.current !== null) {
      window.clearTimeout(presentationTimerRef.current);
      presentationTimerRef.current = null;
    }
  };

  const commitPresentation = () => {
    cancelPresentationFrame();
    if (document.visibilityState === "hidden") return;
    if (!activeProjectionVisibleRef.current || !activeMessagesRef.current) return;
    presentationDirtyRef.current = false;
    messagesRef.current = activeMessagesRef.current;
    setMessages(activeMessagesRef.current);
  };

  const schedulePresentation = () => {
    if (!activeProjectionVisibleRef.current || document.visibilityState === "hidden") return;
    if (presentationFrameRef.current !== null || presentationTimerRef.current !== null) return;
    const callback = () => {
      presentationFrameRef.current = null;
      presentationTimerRef.current = null;
      commitPresentation();
    };
    if (typeof requestAnimationFrame === "function") {
      presentationFrameRef.current = requestAnimationFrame(callback);
    } else {
      presentationTimerRef.current = window.setTimeout(callback, 0);
    }
  };

  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible" && presentationDirtyRef.current) {
        schedulePresentation();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  });

  const clearWorkspaceStatus = (controller: AbortController) => {
    if (abortRef.current !== controller) return;
    if (preparingTimerRef.current !== null) {
      window.clearTimeout(preparingTimerRef.current);
      preparingTimerRef.current = null;
    }
    if (workspaceStatusStateRef.current === "cleared") return;
    const wasShown = workspaceStatusStateRef.current === "shown";
    workspaceStatusStateRef.current = "cleared";
    if (!wasShown) return;
    transitionLifecycle({ type: "clear_workspace_status" }, projectsActiveStream());
  };

  const armWorkspaceStatus = (
    controller: AbortController,
    messagesGeneration: number,
  ) => {
    if (preparingTimerRef.current !== null) {
      window.clearTimeout(preparingTimerRef.current);
    }
    workspaceStatusStateRef.current = "armed";
    preparingTimerRef.current = window.setTimeout(() => {
      preparingTimerRef.current = null;
      if (
        workspaceStatusStateRef.current !== "armed"
        || abortRef.current !== controller
        || controller.signal.aborted
        || messagesGenerationRef.current !== messagesGeneration
      ) return;
      workspaceStatusStateRef.current = "shown";
      transitionLifecycle({ type: "workspace_status" }, projectsActiveStream());
    }, WORKSPACE_STATUS_DELAY_MS);
  };

  const recordStreamStart = (controller: AbortController, requestId: string) => {
    const latency = latencyRef.current;
    if (!latency || latency.controller !== controller) return;
    latency.tracker.recordStreamStart(requestId, performance.now());
  };

  const recordTerminal = (
    controller: AbortController,
    classification: ChatTerminalClassification,
  ) => {
    const latency = latencyRef.current;
    if (!latency || latency.controller !== controller) return;
    latency.tracker.recordTerminal(classification);
  };

  useLayoutEffect(() => {
    const latency = latencyRef.current;
    if (!latency) return;
    const assistant = messages.at(-1);
    if (assistant?.role !== "assistant") return;
    const visible = (assistant.blocks ?? []).some((block) => (
      block.kind === "tool"
      || (block.kind === "reasoning" && Boolean(block.text.trim()))
      || (block.kind === "answer" && Boolean(block.text.trim()))
    ));
    if (!visible) return;
    const renderedAt = performance.now();
    latency.tracker.recordFirstVisible(renderedAt);
    for (const block of assistant.blocks ?? []) {
      if (block.kind === "reasoning" && block.text.trim()) {
        latency.tracker.recordSemantic("reasoning", renderedAt);
      } else if (block.kind === "tool") {
        latency.tracker.recordSemantic("tool", renderedAt);
      } else if (block.kind === "answer" && block.text.trim()) {
        latency.tracker.recordSemantic("answer", renderedAt);
      }
    }
  }, [messages]);

  const applyEvent = (event: ChatEvent, projectToVisible = true) => {
    transitionLifecycle({ type: "event", event }, projectToVisible);
  };

  const reloadCanonical = async (sessionId: string, generation: number) => {
    const detail = await getSession(sessionId);
    let restored = toUiMessages(detail);
    if (stoppedProjectionRef.current?.sessionId === sessionId) {
      restored = stoppedProjectionRef.current.messages;
      stoppedProjectionRef.current = null;
    }
    if (
      messagesGenerationRef.current !== generation
      && !(
        activeMessagesGenerationRef.current === generation
        && activeProjectionVisibleRef.current
        && optionsRef.current.sessionId === sessionId
      )
    ) return null;
    setMessages(restored);
    messagesRef.current = restored;
    activeMessagesRef.current = restored;
    lifecycleRef.current = chatLifecycleReducer(lifecycleRef.current, {
      type: "load",
      messages: restored,
      sessionId,
    });
    return restored;
  };

  const run = (
    draft: ChatDraft,
    request: Parameters<typeof streamChat>[0],
    optimistic: ChatMessage[],
    original: ChatMessage[],
    edit?: EditRequest,
    resumeSessionId?: string,
  ) => {
    const messagesGeneration = ++messagesGenerationRef.current;
    activeMessagesGenerationRef.current = messagesGeneration;
    activeProjectionVisibleRef.current = true;
    busyRef.current = true;
    const controller = new AbortController();
    abortRef.current = controller;
    const question = draft.text;
    promptRef.current = draft;
    activeSessionIdRef.current = request.session_id;
    setSessionError("");
    setMessages(optimistic);
    activeMessagesRef.current = optimistic;
    lifecycleRef.current = chatLifecycleReducer(lifecycleRef.current, {
      type: "start",
      messages: optimistic,
      sessionId: request.session_id,
    });
    setBusy(true);
    latencyRef.current = resumeSessionId ? null : {
      controller,
      tracker: new ChatLatencyTracker(performance.now()),
    };
    workspaceStatusStateRef.current = "cleared";
    void (async () => {
      let sawStreamStart = false;
      let providerExecuted = false;
      let providerStatusChanged = false;
      let sawTerminalEvent = false;
      let streamFailed = false;
      let admissionRejected = false;
      let latestSequence = 0;
      const trackSequence = (sequence: number) => {
        if (sequence > latestSequence) latestSequence = sequence;
      };
      try {
        const initialSource = resumeSessionId
          ? resumeChat(resumeSessionId, {
              signal: controller.signal,
              onSequence: trackSequence,
            })
          : streamChat(request, {
              signal: controller.signal,
              onSequence: trackSequence,
            });
        const source = reconnectChatStream(initialSource, {
          signal: controller.signal,
          getSessionId: () => activeSessionIdRef.current,
          onDisconnect: () => {
            if (projectsActiveStream()) applyEvent({ type: "compaction_status", state: "finished" });
          },
          getAfterSequence: () => latestSequence,
          onSequence: trackSequence,
        });
        // Replayed deltas should catch the UI up immediately. Newly arriving
        // deltas continue to render as they reach the reconnecting browser.
        const smooth = !resumeSessionId && isChatLive() && isChatSmoothStreamingEnabled();
        const smoothed = smooth
          ? createSmoothedChatStream(source, {
              signal: controller.signal,
              isHidden: () => document.visibilityState === "hidden",
            })
          : null;
        if (smoothed) smoothedStreamRef.current = { controller, stream: smoothed };
        for await (const event of smoothed?.events ?? source) {
          if (event.type === "paper_artifact") optionsRef.current.onPaperArtifact?.(event);
          if (event.type === "stream_start") {
            sawStreamStart = true;
            providerExecuted = event.provider_execution !== false;
            recordStreamStart(controller, event.request_id);
          }
          if (event.type === "sandbox_start") {
            armWorkspaceStatus(controller, messagesGeneration);
          }
          if (
            event.type === "sandbox_ready"
            || event.type === "workspace_ready"
            || event.type === "lifecycle"
          ) {
            clearWorkspaceStatus(controller);
          }
          if (
            event.type === "reasoning_start"
            || event.type === "reasoning_delta"
            || event.type === "tool_call"
            || event.type === "tool_call_start"
            || event.type === "tool_call_arguments_delta"
            || event.type === "tool_call_arguments_done"
            || event.type === "app_start"
            || event.type === "app_result"
            || event.type === "artifact_start"
            || event.type === "artifact_ready"
            || event.type === "artifact_error"
            || event.type === "answer_delta"
            || event.type === "done"
            || event.type === "error"
          ) {
            clearWorkspaceStatus(controller);
          }
          if (event.type === "done" || event.type === "error") {
            sawTerminalEvent = true;
            streamFailed = event.type === "error";
            recordTerminal(controller, event.type === "error" ? "error" : "complete");
            if (
              event.type === "error"
              && [
                "openrouter_monthly_budget_exhausted",
                "openrouter_unavailable",
                "openrouter_byok_credential_invalid",
                "openrouter_byok_billing_error",
                "openrouter_byok_rate_limit",
                "hf_inference_billing_exhausted",
              ].includes(event.code ?? "")
            ) {
              providerStatusChanged = true;
              optionsRef.current.onInterrupted(draft);
            }
          }
          const projectsToVisibleConversation = projectsActiveStream();
          const presentationProjects = projectsToVisibleConversation
            && !(smooth && document.visibilityState === "hidden");
          const isDelta = event.type === "reasoning_delta"
            || event.type === "answer_delta"
            || event.type === "tool_call_arguments_delta";
          const isStructural = ![
            "stream_start",
            "sandbox_start",
            "sandbox_ready",
            "workspace_ready",
            "session_title_start",
            "session_title_delta",
            "session_title_done",
            "reasoning_delta",
            "answer_delta",
            "tool_call_arguments_delta",
          ].includes(event.type);
          if (smooth && isStructural) commitPresentation();
          if (
            !controller.signal.aborted
            && (projectsToVisibleConversation
              || event.type === "stream_start"
              || event.type === "session_title_start"
              || event.type === "session_title_delta"
              || event.type === "session_title_done")
          ) {
            if (smooth && isDelta) {
              applyEvent(event, false);
              presentationDirtyRef.current = presentationDirtyRef.current
                || projectsToVisibleConversation;
              schedulePresentation();
            } else {
              applyEvent(event, presentationProjects);
              if (smooth && projectsToVisibleConversation && !presentationProjects) {
                presentationDirtyRef.current = true;
              }
            }
          } else if (!controller.signal.aborted) {
            applyEvent(event, false);
          }
        }
      } catch (error) {
        const completedBeforeReconnect = Boolean(
          resumeSessionId
          && error instanceof ChatStreamError
          && error.code === "chat_not_busy",
        );
        streamFailed = !completedBeforeReconnect;
        if (!controller.signal.aborted) {
          clearWorkspaceStatus(controller);
          if (completedBeforeReconnect) {
            // The turn settled after the session load but before this reconnect.
            // The canonical reload in `finally` replaces the active placeholder.
          } else if (error instanceof ChatStreamError && error.code === "chat_temporarily_disabled") {
            admissionRejected = true;
            setDisabledRequest({ question, draft });
            if (messagesGenerationRef.current === messagesGeneration) {
              setMessages(original);
              messagesRef.current = original;
              setSessionError("");
            }
          } else if (error instanceof ChatStreamError && error.code === "chat_capacity") {
            admissionRejected = true;
            const retryAfterSeconds = error.retryAfterSeconds ?? 5;
            const pending: PendingGeneration = {
              question,
              draft,
              request,
              optimistic,
              original,
              edit,
              retryAfterSeconds,
              retryAt: Date.now() + retryAfterSeconds * 1_000,
            };
            pendingCapacityRef.current = pending;
            setCapacityRequest({
              question,
              draft,
              retryAt: pending.retryAt,
              retryAfterSeconds,
            });
            if (messagesGenerationRef.current === messagesGeneration) {
              setMessages(original);
              messagesRef.current = original;
              setSessionError("");
            }
          } else {
            recordTerminal(controller, "network_error");
            if (
              error instanceof ChatStreamError
              && [
                "paper_context_unavailable",
                "paper_mention_unavailable",
                "paper_mentions_disabled",
                "paper_selection_disabled",
                "paper_selection_requires_reader",
                "paper_selection_paper_mismatch",
                "paper_selection_version_mismatch",
                "paper_selection_page_invalid",
                "paper_selection_too_large",
                "chat_storage_quota_exceeded",
              ].includes(error.code ?? "")
            ) {
              admissionRejected = true;
              optionsRef.current.onInterrupted(draft);
              if (messagesGenerationRef.current === messagesGeneration) {
                setMessages(original);
                messagesRef.current = original;
                setSessionError(error.message);
              }
            }
            if (
              error instanceof ChatStreamError
              && [
                "openrouter_monthly_budget_exhausted",
                "openrouter_unavailable",
                "openrouter_byok_credential_invalid",
                "openrouter_byok_billing_error",
                "openrouter_byok_rate_limit",
                "hf_inference_billing_exhausted",
              ].includes(error.code ?? "")
            ) {
              providerStatusChanged = true;
              optionsRef.current.onInterrupted(draft);
            }
          }
          if (
            !completedBeforeReconnect
            && !admissionRejected
            && messagesGenerationRef.current === messagesGeneration
          ) {
            applyEvent({
              type: "error",
              message: error instanceof Error ? error.message : "The assistant stream failed.",
              code: error instanceof ChatStreamError ? error.code : undefined,
            });
          }
        }
      } finally {
        if (abortRef.current === controller) {
          if (smoothedStreamRef.current?.controller === controller) {
            commitPresentation();
            smoothedStreamRef.current = null;
          }
          clearWorkspaceStatus(controller);
          if (!sawTerminalEvent && !controller.signal.aborted) {
            recordTerminal(controller, "network_error");
          }
          busyRef.current = false;
          setBusy(false);
          if (admissionRejected) {
            optionsRef.current.onSettled(request.session_id);
          } else if (!controller.signal.aborted) {
            if ((sawStreamStart && providerExecuted) || providerStatusChanged) {
              optionsRef.current.onProviderTerminal?.();
            }
            const canonicalId = activeSessionIdRef.current;
            if (edit && !sawStreamStart) {
              if (messagesGenerationRef.current === messagesGeneration) {
                setMessages(edit.snapshot);
                messagesRef.current = edit.snapshot;
                setSessionError("Couldn’t resend this message. Your original conversation was restored.");
              }
            } else if (canonicalId) {
              if (
                messagesGenerationRef.current === messagesGeneration
                && edit && (streamFailed || !sawTerminalEvent)
              ) {
                setMessages(edit.snapshot);
                messagesRef.current = edit.snapshot;
              }
              try {
                const canonical = await reloadCanonical(canonicalId, messagesGeneration);
                if (
                  canonical && edit
                  && canonical.some((message) => message.id === edit.targetId)
                ) {
                  setSessionError("Couldn’t resend this message. Your original conversation was restored.");
                }
              } catch {
                if (messagesGenerationRef.current === messagesGeneration) {
                  transitionLifecycle({ type: "settle" });
                }
              }
            } else if (messagesGenerationRef.current === messagesGeneration) {
              transitionLifecycle({ type: "settle" });
            }
            optionsRef.current.onSettled(canonicalId);
          }
          if (latencyRef.current?.controller === controller) {
            latencyRef.current = null;
          }
        }
      }
    })();
    return true;
  };

  const send = useStableCallback((input: ChatDraft | string) => {
    const draft = typeof input === "string" ? emptyChatDraft(input.trim()) : input;
    const question = draft.text;
    if (!question || question.length > 8_000 || busyRef.current || pendingCapacityRef.current) return false;
    const current = messagesRef.current;
    const latestUser = [...current].reverse().find((message) => message.role === "user");
    const replacement = latestUser?.status && latestUser.status !== "complete" && latestUser.revision
      ? { replace_message_id: latestUser.id, prior_revision: latestUser.revision }
      : null;
    const nextUser: ChatMessage = {
      id: nextId(),
      role: "user",
      text: question,
      paperMentions: draft.paperMentions,
      paperSelection: draft.paperSelection,
    };
    const nextAssistant: ChatMessage = { id: nextId(), role: "assistant", streaming: true, blocks: [] };
    const replaceIndex = replacement && latestUser
      ? findLastMatchingIndex(current, (message) => message.id === latestUser.id)
      : -1;
    const optimistic = replaceIndex < 0
      ? [...current, nextUser, nextAssistant]
      : [...current.slice(0, replaceIndex), nextUser, nextAssistant];
    const viewerContext = optionsRef.current.viewerContext?.();
    return run(draft, {
      message: question,
      paper_mentions: draft.paperMentions.map(({ route_id, title, start, end }) => ({ route_id, title, start, end })),
      session_id: optionsRef.current.sessionId,
      client_message_id: crypto.randomUUID(),
      web_search_enabled: Boolean(optionsRef.current.webSearchEnabled),
      reasoning_effort: optionsRef.current.reasoningEffort ?? "low",
      ...(optionsRef.current.primaryPaperRouteId
        ? { primary_paper_route_id: optionsRef.current.primaryPaperRouteId }
        : {}),
      ...(viewerContext ? { viewer_context: viewerContext } : {}),
      ...(draft.paperSelection ? { paper_selection: toPaperSelectionWire(draft.paperSelection) } : {}),
      ...(!optionsRef.current.sessionId && optionsRef.current.initialModel ? { initial_model: optionsRef.current.initialModel } : {}),
      ...(replacement ?? {}),
    }, optimistic, current);
  });

  const editAndResend = useStableCallback((messageId: string, input: ChatDraft | string) => {
    const draft = typeof input === "string" ? emptyChatDraft(input.trim()) : input;
    const question = draft.text;
    if (!question || question.length > 8_000 || busyRef.current || pendingCapacityRef.current) return false;
    const snapshot = messagesRef.current.slice();
    const targetIndex = snapshot.findIndex(
      (message) => message.id === messageId && message.role === "user",
    );
    if (targetIndex < 0) return false;
    const target = snapshot[targetIndex];
    if (!optionsRef.current.sessionId || !target.revision) return false;
    const nextUser: ChatMessage = {
      id: target.id,
      role: "user",
      text: question,
      paperMentions: draft.paperMentions,
      paperSelection: draft.paperSelection,
      revision: target.revision + 1,
      status: "generating",
    };
    const nextAssistant: ChatMessage = {
      id: nextId(),
      role: "assistant",
      streaming: true,
      blocks: [],
    };
    const optimistic = [...snapshot.slice(0, targetIndex), nextUser, nextAssistant];
    const viewerContext = optionsRef.current.viewerContext?.();
    return run(draft, {
      message: question,
      paper_mentions: draft.paperMentions.map(({ route_id, title, start, end }) => ({ route_id, title, start, end })),
      session_id: optionsRef.current.sessionId,
      client_message_id: crypto.randomUUID(),
      web_search_enabled: Boolean(optionsRef.current.webSearchEnabled),
      reasoning_effort: optionsRef.current.reasoningEffort ?? "low",
      ...(optionsRef.current.primaryPaperRouteId
        ? { primary_paper_route_id: optionsRef.current.primaryPaperRouteId }
        : {}),
      ...(viewerContext ? { viewer_context: viewerContext } : {}),
      ...(draft.paperSelection ? { paper_selection: toPaperSelectionWire(draft.paperSelection) } : {}),
      replace_message_id: target.id,
      prior_revision: target.revision,
    }, optimistic, snapshot, {
      targetId: target.id,
      snapshot,
    });
  });

  const cancelCapacity = useCallback(() => {
    pendingCapacityRef.current = null;
    setCapacityRequest(null);
  }, []);

  const retryCapacity = useStableCallback(() => {
    const pending = pendingCapacityRef.current;
    if (!pending || Date.now() < pending.retryAt || busyRef.current) return false;
    pendingCapacityRef.current = null;
    setCapacityRequest(null);
    return run(
      pending.draft,
      pending.request,
      pending.optimistic,
      pending.original,
      pending.edit,
    );
  });

  const stop = useStableCallback(() => {
    if (!abortRef.current) return;
    const controller = abortRef.current;
    clearWorkspaceStatus(controller);
    recordTerminal(controller, "stopped");
    controller.abort();
    const accepted = smoothedStreamRef.current?.controller === controller
      ? smoothedStreamRef.current.stream.takeAcceptedForStop()
      : [];
    smoothedStreamRef.current = null;
    for (const event of accepted) applyEvent(event, false);
    commitPresentation();
    abortRef.current = null;
    if (latencyRef.current?.controller === controller) {
      latencyRef.current = null;
    }
    busyRef.current = false;
    setBusy(false);
    const stopped = transitionLifecycle({ type: "stop" }, false).messages;
    activeMessagesRef.current = stopped;
    messagesRef.current = stopped;
    setMessages(stopped);
    optionsRef.current.onInterrupted(promptRef.current);
    const sessionId = activeSessionIdRef.current;
    if (sessionId) stoppedProjectionRef.current = { sessionId, messages: stopped };
    if (sessionId) void cancelSession(sessionId).catch(() => undefined);
    const messagesGeneration = ++messagesGenerationRef.current;
    window.setTimeout(() => {
      if (sessionId && messagesGenerationRef.current === messagesGeneration) {
        void reloadCanonical(sessionId, messagesGeneration)
        .catch(() => undefined)
        .finally(() => optionsRef.current.onSettled(sessionId));
      } else if (!sessionId) {
        optionsRef.current.onSettled(null);
      }
    }, 450);
  });

  const toggleBlock = useCallback((messageId: string, blockIndex: number) => setMessages((previous) => previous.map((message) => message.id !== messageId ? message : { ...message, blocks: message.blocks?.map((block, index) => index === blockIndex && (block.kind === "reasoning" || block.kind === "tool") ? { ...block, open: !block.open } : block) })), []);
  const reset = useCallback(() => {
    messagesGenerationRef.current += 1;
    if (preparingTimerRef.current !== null) {
      window.clearTimeout(preparingTimerRef.current);
      preparingTimerRef.current = null;
    }
    workspaceStatusStateRef.current = "cleared";
    abortRef.current?.abort();
    abortRef.current = null;
    smoothedStreamRef.current = null;
    cancelPresentationFrame();
    presentationDirtyRef.current = false;
    stoppedProjectionRef.current = null;
    latencyRef.current = null;
    pendingCapacityRef.current = null;
    setCapacityRequest(null);
    busyRef.current = false;
    activeSessionIdRef.current = null;
    activeMessagesRef.current = null;
    lifecycleRef.current = chatLifecycleReducer(lifecycleRef.current, { type: "reset" });
    activeMessagesGenerationRef.current = null;
    activeProjectionVisibleRef.current = false;
    setMessages([]);
    setBusy(false);
    setSessionError("");
  }, []);
  const load = useStableCallback((
    restored: ChatMessage[],
    sessionId?: string | null,
    resumeActive = false,
  ) => {
    messagesGenerationRef.current += 1;
    if (preparingTimerRef.current !== null) {
      window.clearTimeout(preparingTimerRef.current);
      preparingTimerRef.current = null;
    }
    workspaceStatusStateRef.current = "cleared";
    cancelPresentationFrame();
    presentationDirtyRef.current = false;
    latencyRef.current = null;
    pendingCapacityRef.current = null;
    setCapacityRequest(null);
    if (
      busyRef.current
      && sessionId !== undefined
      && sessionId === activeSessionIdRef.current
      && activeMessagesRef.current
    ) {
      activeProjectionVisibleRef.current = true;
      setMessages(activeMessagesRef.current);
      messagesRef.current = activeMessagesRef.current;
      setSessionError("");
      return;
    }
    activeProjectionVisibleRef.current = false;
    // A route change may replace the visible transcript while another chat is
    // still generating. Keep buffering that stream so it can be reattached if
    // the user returns, without projecting its events into this transcript.
    if (!busyRef.current) {
      abortRef.current?.abort();
      abortRef.current = null;
      activeMessagesRef.current = null;
      activeMessagesGenerationRef.current = null;
      activeProjectionVisibleRef.current = false;
    }
    if (resumeActive && sessionId) {
      const lastUser = [...restored].reverse().find((message) => message.role === "user");
      if (lastUser) {
        const draft: ChatDraft = {
          text: lastUser.text ?? "",
          paperMentions: lastUser.paperMentions ?? [],
          ...(lastUser.paperSelection ? { paperSelection: lastUser.paperSelection } : {}),
        };
        const optimistic = [
          ...restored,
          {
            id: `${lastUser.id}-active`,
            role: "assistant" as const,
            streaming: true,
            blocks: [],
          },
        ];
        run(draft, {
          message: draft.text,
          session_id: sessionId,
          client_message_id: "reconnect",
          web_search_enabled: Boolean(optionsRef.current.webSearchEnabled),
          reasoning_effort: optionsRef.current.reasoningEffort ?? "low",
        }, optimistic, restored, undefined, sessionId);
        return;
      }
    }
    setMessages(restored);
    messagesRef.current = restored;
    lifecycleRef.current = chatLifecycleReducer(lifecycleRef.current, {
      type: "load",
      messages: restored,
      sessionId: sessionId ?? optionsRef.current.sessionId,
    });
    if (!busyRef.current) setBusy(false);
    setSessionError("");
  });

  return {
    messages,
    busy,
    papers,
    sessionError,
    capacityRequest,
    disabledRequest,
    send,
    editAndResend,
    retryCapacity,
    cancelCapacity,
    dismissDisabled: () => setDisabledRequest(null),
    stop,
    toggleBlock,
    reset,
    load,
  };
}

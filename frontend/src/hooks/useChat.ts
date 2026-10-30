import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { chatApi } from "@/lib/api/chat";
import {
  type ChatDraft,
  type ChatEvent,
  type ChatMessage,
  type ChatStreamRequest,
  type ReasoningEffort,
  ChatStreamError,
  DEFAULT_REASONING_EFFORT,
  collectChatPapers,
  draftFromMessage,
  isChatLive,
  isChatSmoothStreamingEnabled,
  latestUserMessage,
  resumeChat,
  streamChat,
} from "@/lib/chat";
import { emptyChatDraft } from "@/lib/paperSelection";
import { buildChatRequest, draftRequestFields, primaryPaperField } from "@/lib/chatRequest";
import {
  ChatLatencyTracker,
  type ChatTerminalClassification,
} from "@/lib/chatLatency";
import {
  EVENT_TRAITS,
  type ChatLifecycleAction,
  findLastMatchingIndex,
  toggleChatBlock,
} from "@/lib/chatLifecycle";
import {
  createSmoothedChatStream,
  type SmoothedChatStream,
} from "@/lib/chatStreamSmoother";
import { reconnectChatStream } from "@/lib/chatReconnect";
import { ChatTurn, type EditRequest, type PendingGeneration, type ChatTurnConfiguration } from "@/lib/chatTurn";
import { toUiMessages, type ChatSessionDetail } from "@/lib/chatSessions";

const WORKSPACE_STATUS_DELAY_MS = 750;
const MAX_QUESTION_LENGTH = 8_000;
const STREAM_FAILED = "The assistant stream failed.";
const RESEND_FAILED = "Couldn’t resend this message. Your original conversation was restored.";

function useStableCallback<Args extends unknown[], Result>(
  callback: (...args: Args) => Result,
): (...args: Args) => Result {
  const callbackRef = useRef(callback);
  useLayoutEffect(() => {
    callbackRef.current = callback;
  });
  return useCallback((...args: Args) => callbackRef.current(...args), []);
}

const streamingAssistant = (id: string): ChatMessage => ({ id, role: "assistant", streaming: true, blocks: [] });

interface UseChatOptions {
  sessionId: string | null;
  initialModel?: string;
  webSearchEnabled?: boolean;
  reasoningEffort?: ReasoningEffort;
  onSessionId: (id: string, originSessionId: string | null, configuration: ChatTurn["configuration"]) => void;
  onTitle: (title: string, sessionId: string | null) => void;
  onSettled: (sessionId: string | null) => void;
  onProviderTerminal?: () => void;
  onPaperArtifact?: (event: Extract<ChatEvent, { type: "paper_artifact" }>, sessionId: string | null) => void;
  loadSession?: (sessionId: string) => Promise<ChatSessionDetail>;
  onInterrupted: (draft: ChatDraft) => void;
  primaryPaperRouteId?: string;
  viewerContext?: () => { page: number } | undefined;
}

/**
 * The selected conversation's transcript and its one active turn.
 *
 * `ChatTurn` is the store: it owns the active turn and the transcript shown for
 * the selected conversation, which is either a projection of that turn or a
 * loaded transcript. View epochs keep a turn that has lost the selected
 * conversation from writing into the one that replaced it.
 */
export function useChat(options: UseChatOptions) {
  const [turn] = useState(() => new ChatTurn());
  const snapshot = useSyncExternalStore(turn.subscribe, turn.getSnapshot);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  /* Ownership of the selected conversation. */
  const abortRef = useRef<AbortController | null>(null);
  // Bumped whenever the selected conversation starts showing another transcript.
  const viewEpochRef = useRef(0);
  // The view epoch the active turn started in.
  const activeEpochRef = useRef<number | null>(null);
  // Whether the selected conversation shows the active turn's projection.
  const projectingRef = useRef(false);
  const selectedSessionRef = useRef(options.sessionId);

  /* Presentation of the active stream. */
  const smoothedStreamRef = useRef<{ controller: AbortController; stream: SmoothedChatStream } | null>(null);
  const presentationFrameRef = useRef<{ cancel: () => void } | null>(null);
  const presentationDirtyRef = useRef(false);
  const workspaceStatusRef = useRef<{ state: "armed" | "shown" | "cleared"; timer: number | null }>({
    state: "cleared",
    timer: null,
  });
  const latencyRef = useRef<{ controller: AbortController; tracker: ChatLatencyTracker } | null>(null);
  const stoppedProjectionRef = useRef<{ sessionId: string; messages: ChatMessage[] } | null>(null);
  const promptRef = useRef<ChatDraft>(emptyChatDraft());
  const idRef = useRef(0);

  // Returning to a running turn shows its projection in this very render,
  // so the previous conversation's transcript never renders under the new route.
  const switchingSession = selectedSessionRef.current !== options.sessionId;
  const messages = (switchingSession ? turn.projectSession(options.sessionId) : null) ?? snapshot.messages;
  const busy = snapshot.busy;

  const cancelPresentationFrame = () => {
    presentationFrameRef.current?.cancel();
    presentationFrameRef.current = null;
  };

  const disarmWorkspaceStatus = () => {
    const status = workspaceStatusRef.current;
    if (status.timer !== null) window.clearTimeout(status.timer);
    workspaceStatusRef.current = { state: "cleared", timer: null };
  };

  /** Stop all stream timers; used when the hook unmounts. */
  const teardownStream = useStableCallback(() => {
    const { timer } = workspaceStatusRef.current;
    if (timer !== null) window.clearTimeout(timer);
    abortRef.current?.abort();
    smoothedStreamRef.current = null;
    cancelPresentationFrame();
    turn.cancelCapacity();
  });
  useEffect(() => teardownStream, [teardownStream]);

  useLayoutEffect(() => {
    if (selectedSessionRef.current !== options.sessionId) {
      selectedSessionRef.current = options.sessionId;
      if (turn.sessionId !== options.sessionId) {
        viewEpochRef.current += 1;
        latencyRef.current = null;
      }
    }
    const projection = turn.projectSession(options.sessionId);
    projectingRef.current = projection !== null;
    if (projection) turn.present({ messages: projection });
  }, [options.sessionId, turn]);
  useEffect(() => {
    if (!turn.busy) turn.restore(turn.messages, { sessionId: options.sessionId });
  }, [options.sessionId, turn]);

  const papers = useMemo(() => collectChatPapers(messages), [messages]);

  const nextId = () => `m${++idRef.current}_${Date.now().toString(36)}`;
  const transitionLifecycle = (
    action: ChatLifecycleAction,
    projectToVisible = true,
  ) => {
    const previous = turn.state;
    const next = turn.transition(action, projectToVisible);
    const announcedSessionId = action.type === "event"
      && action.event.type === "stream_start"
      ? action.event.session_id
      : null;
    if (announcedSessionId) {
      optionsRef.current.onSessionId(announcedSessionId, previous.sessionId, turn.configuration);
    } else if (next.sessionId && next.sessionId !== previous.sessionId) {
      optionsRef.current.onSessionId(next.sessionId, previous.sessionId, turn.configuration);
    }
    if (next.title !== previous.title) optionsRef.current.onTitle(next.title, next.sessionId);
    return next;
  };

  const applyEvent = (event: ChatEvent, projectToVisible = true) => {
    transitionLifecycle({ type: "event", event }, projectToVisible);
  };

  const projectsActiveStream = () => (
    activeEpochRef.current === viewEpochRef.current
    || projectingRef.current
  );

  /** Restore a transcript after a failed turn; it is shown only while the
   * turn's view epoch still owns the selected conversation. */
  const restoreTranscript = (
    restored: ChatMessage[],
    epoch: number,
    sessionError: string,
    view: { disabledRequest?: { question: string; draft: ChatDraft } } = {},
  ) => {
    const owned = viewEpochRef.current === epoch;
    turn.restore(restored, { show: owned, view: { ...view, ...(owned ? { sessionError } : {}) } });
  };

  const commitPresentation = () => {
    cancelPresentationFrame();
    if (document.visibilityState === "hidden") return;
    if (!projectingRef.current) return;
    presentationDirtyRef.current = false;
    turn.present({ messages: turn.messages });
  };

  const schedulePresentation = () => {
    if (!projectingRef.current || document.visibilityState === "hidden") return;
    if (presentationFrameRef.current !== null) return;
    const callback = () => {
      presentationFrameRef.current = null;
      commitPresentation();
    };
    if (typeof requestAnimationFrame === "function") {
      const frame = requestAnimationFrame(callback);
      presentationFrameRef.current = { cancel: () => cancelAnimationFrame(frame) };
    } else {
      const timer = window.setTimeout(callback, 0);
      presentationFrameRef.current = { cancel: () => window.clearTimeout(timer) };
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
    const { state } = workspaceStatusRef.current;
    disarmWorkspaceStatus();
    if (state !== "shown") return;
    transitionLifecycle({ type: "clear_workspace_status" }, projectsActiveStream());
  };

  const armWorkspaceStatus = (controller: AbortController, epoch: number) => {
    const { timer: previous } = workspaceStatusRef.current;
    if (previous !== null) window.clearTimeout(previous);
    const timer = window.setTimeout(() => {
      workspaceStatusRef.current = { ...workspaceStatusRef.current, timer: null };
      if (
        workspaceStatusRef.current.state !== "armed"
        || abortRef.current !== controller
        || controller.signal.aborted
        || viewEpochRef.current !== epoch
      ) return;
      workspaceStatusRef.current = { state: "shown", timer: null };
      transitionLifecycle({ type: "workspace_status" }, projectsActiveStream());
    }, WORKSPACE_STATUS_DELAY_MS);
    workspaceStatusRef.current = { state: "armed", timer };
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

  const reloadCanonical = async (sessionId: string, epoch: number) => {
    const loadSession = optionsRef.current.loadSession ?? ((id: string) => chatApi.getSession(id));
    const detail = await loadSession(sessionId);
    let restored = toUiMessages(detail);
    if (stoppedProjectionRef.current?.sessionId === sessionId) {
      restored = stoppedProjectionRef.current.messages;
      stoppedProjectionRef.current = null;
    }
    if (
      viewEpochRef.current !== epoch
      && !(
        activeEpochRef.current === epoch
        && projectingRef.current
        && optionsRef.current.sessionId === sessionId
      )
    ) return null;
    turn.restore(restored, { sessionId, show: true });
    return restored;
  };

  const buildRequest = (message: string, target: Parameters<typeof buildChatRequest>[2]) => (
    buildChatRequest(optionsRef.current, message, target)
  );

  /** A sendable draft, or null while a turn is running or waiting for capacity. */
  const admitDraft = (input: ChatDraft | string): ChatDraft | null => {
    const draft = typeof input === "string" ? emptyChatDraft(input.trim()) : input;
    if (!draft.text || draft.text.length > MAX_QUESTION_LENGTH || turn.busy || turn.pendingCapacity) return null;
    return draft;
  };

  const run = (
    draft: ChatDraft,
    request: ChatStreamRequest,
    optimistic: ChatMessage[],
    original: ChatMessage[],
    edit?: EditRequest,
    resumeSessionId?: string,
    configuration?: ChatTurnConfiguration,
  ) => {
    const epoch = ++viewEpochRef.current;
    activeEpochRef.current = epoch;
    projectingRef.current = true;
    const controller = new AbortController();
    abortRef.current = controller;
    const question = draft.text;
    promptRef.current = draft;
    turn.start(optimistic, request.session_id, configuration ?? {
      model: optionsRef.current.initialModel,
      webSearchEnabled: Boolean(request.web_search_enabled),
      reasoningEffort: request.reasoning_effort ?? DEFAULT_REASONING_EFFORT,
    });
    latencyRef.current = resumeSessionId ? null : {
      controller,
      tracker: new ChatLatencyTracker(performance.now()),
    };
    workspaceStatusRef.current = { ...workspaceStatusRef.current, state: "cleared" };
    void (async () => {
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
          getSessionId: () => turn.sessionId,
          onDisconnect: () => {
            if (!controller.signal.aborted && abortRef.current === controller) {
              applyEvent({ type: "compaction_status", state: "finished" }, projectsActiveStream());
            }
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
          if (controller.signal.aborted || abortRef.current !== controller) break;
          const traits = EVENT_TRAITS[event.type];
          if (event.type === "paper_artifact") optionsRef.current.onPaperArtifact?.(event, turn.sessionId);
          if (event.type === "stream_start") recordStreamStart(controller, event.request_id);
          if (traits.workspaceStatus === "arm") armWorkspaceStatus(controller, epoch);
          if (traits.workspaceStatus === "clear") clearWorkspaceStatus(controller);
          if (turn.observe(event) && projectsActiveStream()) optionsRef.current.onInterrupted(draft);
          if (traits.terminal) recordTerminal(controller, traits.terminal);
          const projectsToVisibleConversation = projectsActiveStream();
          const presentationProjects = projectsToVisibleConversation
            && !(smooth && document.visibilityState === "hidden");
          if (smooth && traits.presentation === "structural") commitPresentation();
          if (smooth && traits.presentation === "delta") {
            applyEvent(event, false);
            presentationDirtyRef.current ||= projectsToVisibleConversation;
            schedulePresentation();
          } else {
            applyEvent(event, presentationProjects);
            if (smooth && projectsToVisibleConversation && !presentationProjects) {
              presentationDirtyRef.current = true;
            }
          }
        }
      } catch (error) {
        if (!controller.signal.aborted && abortRef.current === controller) {
          const rejection = turn.reject(error, Boolean(resumeSessionId));
          clearWorkspaceStatus(controller);
          if (rejection === "completed") {
            // The turn settled after the session load but before this reconnect.
            // The canonical reload in `finally` replaces the active placeholder.
          } else if (rejection === "disabled") {
            restoreTranscript(original, epoch, "", { disabledRequest: { question, draft } });
          } else if (rejection === "capacity") {
            const retryAfterSeconds = error instanceof ChatStreamError ? error.retryAfterSeconds ?? 5 : 5;
            turn.queueCapacity({
              question,
              draft,
              request,
              optimistic,
              original,
              edit,
              retryAfterSeconds,
              retryAt: Date.now() + retryAfterSeconds * 1_000,
            });
            restoreTranscript(original, epoch, "");
          } else {
            recordTerminal(controller, "network_error");
            if (rejection === "draft") {
              if (projectsActiveStream()) optionsRef.current.onInterrupted(draft);
              restoreTranscript(original, epoch, error instanceof Error ? error.message : STREAM_FAILED);
            }
            if (rejection === "provider" && projectsActiveStream()) {
              optionsRef.current.onInterrupted(draft);
            }
          }
          if (
            rejection !== "completed"
            && !turn.admissionRejected
            && viewEpochRef.current === epoch
          ) {
            applyEvent({
              type: "error",
              message: error instanceof Error ? error.message : STREAM_FAILED,
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
          if (!turn.sawTerminalEvent && !controller.signal.aborted) {
            recordTerminal(controller, "network_error");
          }
          turn.finish();
          if (turn.admissionRejected) {
            optionsRef.current.onSettled(request.session_id);
          } else if (!controller.signal.aborted) {
            if (turn.shouldRefreshProvider) {
              optionsRef.current.onProviderTerminal?.();
            }
            const canonicalId = turn.sessionId;
            const owned = viewEpochRef.current === epoch;
            if (edit && !turn.sawStreamStart) {
              restoreTranscript(edit.snapshot, epoch, RESEND_FAILED);
            } else if (canonicalId) {
              if (owned && edit && (turn.streamFailed || !turn.sawTerminalEvent)) {
                turn.restore(edit.snapshot, { show: true });
              }
              try {
                const canonical = await reloadCanonical(canonicalId, epoch);
                if (
                  canonical && edit
                  && canonical.some((message) => message.id === edit.targetId)
                ) {
                  turn.present({ sessionError: RESEND_FAILED });
                }
              } catch {
                if (viewEpochRef.current === epoch) {
                  transitionLifecycle({ type: "settle" });
                }
              }
            } else if (owned) {
              transitionLifecycle({ type: "settle" });
            }
            // Navigation can detach a finished turn while its reload is pending.
            // Notify its completion unless another turn has taken ownership.
            if (!abortRef.current || abortRef.current === controller) {
              optionsRef.current.onSettled(canonicalId);
            }
          }
          if (latencyRef.current?.controller === controller) {
            latencyRef.current = null;
          }
        }
      }
    })();
    return true;
  };

  /* ---------- Commands ---------- */

  const send = useStableCallback((input: ChatDraft | string) => {
    const draft = admitDraft(input);
    if (!draft) return false;
    const current = turn.visibleMessages;
    const latestUser = latestUserMessage(current);
    const replacement = latestUser?.status && latestUser.status !== "complete" && latestUser.revision
      ? { replace_message_id: latestUser.id, prior_revision: latestUser.revision }
      : null;
    const nextUser: ChatMessage = {
      id: nextId(),
      role: "user",
      text: draft.text,
      paperMentions: draft.paperMentions,
      paperSelection: draft.paperSelection,
    };
    const nextAssistant = streamingAssistant(nextId());
    const replaceIndex = replacement && latestUser
      ? findLastMatchingIndex(current, (message) => message.id === latestUser.id)
      : -1;
    const optimistic = replaceIndex < 0
      ? [...current, nextUser, nextAssistant]
      : [...current.slice(0, replaceIndex), nextUser, nextAssistant];
    const { sessionId, initialModel } = optionsRef.current;
    return run(draft, buildRequest(draft.text, {
      session_id: sessionId,
      client_message_id: crypto.randomUUID(),
      ...draftRequestFields(optionsRef.current, draft),
      ...(!sessionId && initialModel ? { initial_model: initialModel } : {}),
      ...(replacement ?? {}),
    }), optimistic, current);
  });

  const editAndResend = useStableCallback((messageId: string, input: ChatDraft | string) => {
    const draft = admitDraft(input);
    if (!draft) return false;
    const snapshot = turn.visibleMessages.slice();
    const targetIndex = snapshot.findIndex(
      (message) => message.id === messageId && message.role === "user",
    );
    if (targetIndex < 0) return false;
    const target = snapshot[targetIndex];
    const { sessionId } = optionsRef.current;
    if (!sessionId || !target.revision) return false;
    const nextUser: ChatMessage = {
      id: target.id,
      role: "user",
      text: draft.text,
      paperMentions: draft.paperMentions,
      paperSelection: draft.paperSelection,
      revision: target.revision + 1,
      status: "generating",
    };
    const optimistic = [...snapshot.slice(0, targetIndex), nextUser, streamingAssistant(nextId())];
    return run(draft, buildRequest(draft.text, {
      session_id: sessionId,
      client_message_id: crypto.randomUUID(),
      ...draftRequestFields(optionsRef.current, draft),
      replace_message_id: target.id,
      prior_revision: target.revision,
    }), optimistic, snapshot, {
      targetId: target.id,
      snapshot,
    });
  });

  const retryFromProgress = useStableCallback(() => {
    const snapshot = turn.visibleMessages.slice();
    const latestUser = latestUserMessage(snapshot);
    const { sessionId } = optionsRef.current;
    if (!sessionId || !latestUser?.revision || turn.busy || turn.pendingCapacity) return false;
    const draft = emptyChatDraft(latestUser.text ?? "Continue the interrupted response from saved progress.");
    const optimistic: ChatMessage[] = [...snapshot,
      { id: nextId(), role: "user", text: draft.text, paperMentions: [] },
      streamingAssistant(nextId()),
    ];
    return run(draft, buildRequest(draft.text, {
      session_id: sessionId,
      client_message_id: crypto.randomUUID(),
      retry_message_id: latestUser.id,
      ...primaryPaperField(optionsRef.current),
    }), optimistic, snapshot);
  });

  const retryLatest = useStableCallback(() => {
    const latestUser = latestUserMessage(turn.visibleMessages);
    if (!latestUser?.text) return false;
    return editAndResend(latestUser.id, draftFromMessage(latestUser));
  });

  const cancelCapacity = useCallback(() => {
    turn.cancelCapacity();
  }, [turn]);

  const retryCapacity = useStableCallback(() => {
    const pending = turn.pendingCapacity;
    if (!pending || Date.now() < pending.retryAt || turn.busy) return false;
    turn.cancelCapacity();
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
    turn.finish();
    const visible = projectsActiveStream();
    const stopped = transitionLifecycle({ type: "stop" }, visible).messages;
    if (visible) optionsRef.current.onInterrupted(promptRef.current);
    const sessionId = turn.sessionId;
    if (sessionId) stoppedProjectionRef.current = { sessionId, messages: stopped };
    if (sessionId) void chatApi.cancelSession(sessionId).catch(() => undefined);
    const epoch = ++viewEpochRef.current;
    window.setTimeout(() => {
      if (sessionId && visible && viewEpochRef.current === epoch) {
        void reloadCanonical(sessionId, epoch)
        .catch(() => undefined)
        .finally(() => {
          if (!abortRef.current) optionsRef.current.onSettled(sessionId);
        });
      } else if (!abortRef.current) {
        optionsRef.current.onSettled(sessionId);
      }
    }, 450);
  });

  const toggleBlock = useStableCallback((messageId: string, blockIndex: number) => {
    if (projectingRef.current) {
      turn.transition({ type: "toggle_block", messageId, blockIndex }, true);
    } else {
      turn.present({ messages: toggleChatBlock(turn.visibleMessages, messageId, blockIndex) });
    }
  });

  /** The selected conversation is about to show another transcript. */
  const detachView = () => {
    viewEpochRef.current += 1;
    disarmWorkspaceStatus();
    cancelPresentationFrame();
    presentationDirtyRef.current = false;
    latencyRef.current = null;
  };

  const abortStream = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    activeEpochRef.current = null;
  };

  const reset = useStableCallback(() => {
    detachView();
    abortStream();
    smoothedStreamRef.current = null;
    stoppedProjectionRef.current = null;
    projectingRef.current = false;
    turn.reset();
  });

  const load = useStableCallback((
    restored: ChatMessage[],
    sessionId?: string | null,
    resumeActive = false,
    configuration?: ChatTurnConfiguration,
  ) => {
    detachView();
    turn.cancelCapacity();
    if (
      turn.busy
      && sessionId !== undefined
      && sessionId === turn.sessionId
    ) {
      projectingRef.current = true;
      turn.present({ messages: turn.messages, sessionError: "" });
      return;
    }
    projectingRef.current = false;
    // A route change may replace the visible transcript while another chat is
    // still generating. Keep buffering that stream so it can be reattached if
    // the user returns, without projecting its events into this transcript.
    if (!turn.busy) abortStream();
    if (resumeActive && sessionId && !turn.busy) {
      const lastUser = latestUserMessage(restored);
      if (lastUser) {
        const draft = draftFromMessage(lastUser);
        const optimistic = [...restored, streamingAssistant(`${lastUser.id}-active`)];
        run(draft, buildRequest(draft.text, {
          session_id: sessionId,
          client_message_id: "reconnect",
        }), optimistic, restored, undefined, sessionId, configuration);
        return;
      }
    }
    if (turn.busy) {
      turn.present({ messages: restored, sessionError: "" });
    } else {
      turn.restore(restored, {
        sessionId: sessionId ?? optionsRef.current.sessionId,
        show: true,
        view: { sessionError: "" },
      });
    }
  });

  const capacityRequest: Pick<
    PendingGeneration,
    "question" | "draft" | "retryAt" | "retryAfterSeconds"
  > | null = snapshot.capacityRequest;

  return {
    messages,
    busy,
    activeSessionId: busy ? turn.sessionId : null,
    activeTitle: turn.state.title,
    activeConfiguration: turn.configuration,
    selectedBusy: busy && turn.sessionId === options.sessionId,
    papers,
    sessionError: snapshot.sessionError,
    capacityRequest,
    disabledRequest: snapshot.disabledRequest,
    send,
    editAndResend,
    retryFromProgress,
    retryLatest,
    retryCapacity,
    cancelCapacity,
    dismissDisabled: () => turn.present({ disabledRequest: null }),
    stop,
    toggleBlock,
    reset,
    load,
  };
}

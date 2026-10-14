import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { AssistantMessage, UserMessage } from "./ChatMessage";
import type { ChatDraft, ChatMessage, ChatPaperHit } from "@/lib/chat";

interface ChatConversationProps {
  messages: ChatMessage[];
  papers: Record<string, ChatPaperHit>;
  busy: boolean;
  queuedDraft?: ChatDraft;
  paperMentionsEnabled: boolean;
  archivePending: "old" | "oldest" | null;
  openRouterFallbackEnabled: boolean;
  onToggleBlock: (messageId: string, blockIndex: number) => void;
  onEditAndResend: (messageId: string, draft: ChatDraft) => boolean;
  onRetryFromProgress?: () => boolean;
  onRetryWithLuna?: () => void;
  onArchiveOld: () => void;
  onArchiveOldest: () => void;
}

export function ChatConversation({
  messages,
  papers,
  busy,
  queuedDraft,
  paperMentionsEnabled,
  archivePending,
  openRouterFallbackEnabled,
  onToggleBlock,
  onEditAndResend,
  onRetryFromProgress,
  onRetryWithLuna,
  onArchiveOld,
  onArchiveOldest,
}: ChatConversationProps) {
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollTopBeforeToggleRef = useRef<number | null>(null);
  // "bottom" follows streamed content, "question" keeps the latest question
  // pinned near the top while its answer grows below, "free" never moves.
  const scrollModeRef = useRef<"bottom" | "question" | "free">("bottom");
  const questionScrollTopRef = useRef(0);
  const appliedScrollTopRef = useRef(0);
  const [hasContentBelow, setHasContentBelow] = useState(false);
  const touchYRef = useRef<number | null>(null);
  const setScrollMode = useCallback((mode: "bottom" | "question" | "free") => {
    scrollModeRef.current = mode;
  }, []);
  const updateContentBelow = useCallback(() => {
    const scroller = scrollRef.current;
    if (scroller) {
      setHasContentBelow(scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight > 1);
    }
  }, []);
  const userMessages = messages.filter((message) => message.role === "user");
  const userCount = userMessages.length;
  // An idle conversation opens at the latest content; one that opens
  // mid-stream (including a first send from the empty composer) pins its question.
  const previousUserCountRef = useRef(userCount);
  const previousBusyRef = useRef(false);
  const firstUserId = userMessages[0]?.id;
  const latestUserId = userMessages.at(-1)?.id;

  useEffect(() => {
    if (busy) setEditingMessageId(null);
  }, [busy]);

  useLayoutEffect(() => {
    const scrollElement = scrollRef.current;
    if (!scrollElement) return;
    // Canonical reloads replace optimistic IDs without adding a new question.
    if (userCount > previousUserCountRef.current || (busy && !previousBusyRef.current)) {
      const question = Array.from(scrollElement.querySelectorAll<HTMLElement>("[data-message-id]")).at(-1);
      if (question) {
        const containerTop = scrollElement.getBoundingClientRect().top;
        questionScrollTopRef.current = scrollElement.scrollTop
          + question.getBoundingClientRect().top - containerTop - 24;
        setScrollMode("question");
      }
    }
    previousUserCountRef.current = userCount;
    previousBusyRef.current = busy;
    if (scrollTopBeforeToggleRef.current !== null) {
      scrollElement.scrollTop = scrollTopBeforeToggleRef.current;
      scrollTopBeforeToggleRef.current = null;
      return;
    }
    if (scrollModeRef.current === "bottom") scrollElement.scrollTop = scrollElement.scrollHeight;
    if (scrollModeRef.current === "question") {
      // Until the answer is tall enough, the browser clamps this to the end;
      // once the question reaches the top, the reader's view stops moving.
      scrollElement.scrollTop = questionScrollTopRef.current;
      appliedScrollTopRef.current = scrollElement.scrollTop;
    }
  }, [messages, userCount, busy, setScrollMode]);

  // Button visibility follows the actual viewport, independently of whether
  // streaming is allowed to move the reader's position.
  useLayoutEffect(updateContentBelow);

  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller) return;
    const observer = new ResizeObserver(updateContentBelow);
    observer.observe(scroller);
    if (scroller.firstElementChild) observer.observe(scroller.firstElementChild);
    return () => observer.disconnect();
  }, [updateContentBelow]);

  const toggleBlock = (messageId: string, blockIndex: number) => {
    scrollTopBeforeToggleRef.current = scrollRef.current?.scrollTop ?? null;
    onToggleBlock(messageId, blockIndex);
  };

  return (
    <div className="chat-conversation-viewport">
    <div
      className="chat-conversation"
      ref={scrollRef}
      tabIndex={0}
      role="region"
      aria-label="Conversation"
      onWheel={(event) => {
        if (event.deltaY < 0 || scrollModeRef.current === "question") setScrollMode("free");
      }}
      onTouchStart={(event) => { touchYRef.current = event.touches[0]?.clientY ?? null; }}
      onTouchMove={(event) => {
        const y = event.touches[0]?.clientY;
        if (y !== undefined && touchYRef.current !== null
          && (y > touchYRef.current || scrollModeRef.current === "question")) setScrollMode("free");
        touchYRef.current = y ?? null;
      }}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        if (["ArrowUp", "PageUp", "Home"].includes(event.key) || (event.key === " " && event.shiftKey)) {
          setScrollMode("free");
        }
        if (["ArrowDown", "PageDown", "End", " "].includes(event.key) && scrollModeRef.current === "question") {
          setScrollMode("free");
        }
      }}
      onScroll={(event) => {
        const { scrollHeight, scrollTop, clientHeight } = event.currentTarget;
        const atEnd = scrollHeight - scrollTop - clientHeight <= 1;
        // Scrolling away also covers scrollbar dragging. Only explicit actions
        // resume following, so delayed scroll events cannot undo upward intent.
        if (scrollModeRef.current === "bottom" && !atEnd) setScrollMode("free");
        // A pinned question only moves up when a shrinking viewport clamps it.
        const moved = scrollTop - appliedScrollTopRef.current;
        if (scrollModeRef.current === "question" && (moved > 1 || (moved < -1 && !atEnd))) setScrollMode("free");
        updateContentBelow();
      }}
    >
      <div className="chat-conversation-inner">
        {messages.length === 0 && queuedDraft?.text && <UserMessage
          id="queued-launch-preview"
          text={queuedDraft.text}
          paperMentions={queuedDraft.paperMentions}
          paperSelection={queuedDraft.paperSelection}
          isInitial
        />}
        {messages.map((message) => message.role === "user"
          ? <UserMessage
              key={message.id}
              id={message.id}
              text={message.text ?? ""}
              paperMentions={message.paperMentions ?? []}
              paperSelection={message.paperSelection}
              paperMentionsEnabled={paperMentionsEnabled}
              isInitial={message.id === firstUserId}
              editingAllowed={!busy && Boolean(message.revision)}
              editing={editingMessageId === message.id}
              editNotice={message.id === firstUserId
                ? "Sending will replace this conversation."
                : message.id === latestUserId
                  ? "Sending will replace the response."
                  : "Sending will replace the response and all messages after it."}
              onEdit={() => setEditingMessageId(message.id)}
              onCancel={() => setEditingMessageId(null)}
              onResendDraft={(nextDraft) => {
                const accepted = onEditAndResend(message.id, nextDraft);
                if (accepted) setEditingMessageId(null);
                return accepted;
              }}
            />
          : <AssistantMessage
              key={message.id}
              msg={message}
              papers={papers}
              onToggleBlock={toggleBlock}
              onRetryCompaction={!busy && message.id === messages.at(-1)?.id && userMessages.at(-1)?.revision
                ? onRetryFromProgress
                : undefined}
              onRetryWithLuna={!busy && message.id === messages.at(-1)?.id && userMessages.at(-1)?.revision
                ? onRetryWithLuna
                : undefined}
              onArchiveOldChats={onArchiveOld}
              onArchiveOldestChats={onArchiveOldest}
              archivePending={archivePending}
              hfBilling={null}
              openRouterFallbackEnabled={openRouterFallbackEnabled}
              feedbackEnabled
            />)}
      </div>
    </div>
    {hasContentBelow && <button
      type="button"
      className="chat-jump-latest"
      onClick={() => {
        setScrollMode("bottom");
        const scroller = scrollRef.current;
        if (scroller) {
          scroller.focus({ preventScroll: true });
          scroller.scrollTop = scroller.scrollHeight;
          updateContentBelow();
        }
      }}
    >Jump to latest</button>}
    </div>
  );
}

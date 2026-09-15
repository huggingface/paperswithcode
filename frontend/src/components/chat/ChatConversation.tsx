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
  onArchiveOld,
  onArchiveOldest,
}: ChatConversationProps) {
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollTopBeforeToggleRef = useRef<number | null>(null);
  const editScrollAnchorRef = useRef<string | null>(null);
  const followingBottomRef = useRef(true);
  const [followingBottom, setFollowingBottom] = useState(true);
  const touchYRef = useRef<number | null>(null);
  const followBottom = useCallback((follow: boolean) => {
    followingBottomRef.current = follow;
    setFollowingBottom(follow);
  }, []);
  const previousUserCountRef = useRef(0);
  const previousBusyRef = useRef(false);
  const userMessages = messages.filter((message) => message.role === "user");
  const userCount = userMessages.length;
  const firstUserId = userMessages[0]?.id;
  const latestUserId = userMessages.at(-1)?.id;

  useEffect(() => {
    if (busy) setEditingMessageId(null);
    else editScrollAnchorRef.current = null;
  }, [busy]);

  useLayoutEffect(() => {
    const scrollElement = scrollRef.current;
    if (!scrollElement) return;
    // Canonical reloads replace optimistic IDs without adding a new question.
    if (userCount > previousUserCountRef.current || (busy && !previousBusyRef.current)) {
      followBottom(true);
    }
    previousUserCountRef.current = userCount;
    previousBusyRef.current = busy;
    if (scrollTopBeforeToggleRef.current !== null) {
      scrollElement.scrollTop = scrollTopBeforeToggleRef.current;
      scrollTopBeforeToggleRef.current = null;
      return;
    }
    if (editScrollAnchorRef.current) {
      const target = Array.from(
        scrollElement.querySelectorAll<HTMLElement>("[data-message-id]"),
      ).find((element) => element.dataset.messageId === editScrollAnchorRef.current);
      editScrollAnchorRef.current = null;
      if (target) {
        const containerRect = scrollElement.getBoundingClientRect();
        const targetRect = target.getBoundingClientRect();
        scrollElement.scrollTop += targetRect.top - containerRect.top - 24;
        followBottom(false);
        return;
      }
    }
    if (followingBottomRef.current) scrollElement.scrollTop = scrollElement.scrollHeight;
  }, [messages, userCount, busy, followBottom]);

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
        if (event.deltaY < 0) followBottom(false);
      }}
      onTouchStart={(event) => { touchYRef.current = event.touches[0]?.clientY ?? null; }}
      onTouchMove={(event) => {
        const y = event.touches[0]?.clientY;
        if (y !== undefined && touchYRef.current !== null && y > touchYRef.current) followBottom(false);
        touchYRef.current = y ?? null;
      }}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        if (["ArrowUp", "PageUp", "Home"].includes(event.key) || (event.key === " " && event.shiftKey)) {
          followBottom(false);
        }
      }}
      onScroll={(event) => {
        const { scrollHeight, scrollTop, clientHeight } = event.currentTarget;
        // Scrolling away also covers scrollbar dragging. Only explicit actions
        // resume following, so delayed scroll events cannot undo upward intent.
        if (scrollHeight - scrollTop - clientHeight > 1) followBottom(false);
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
                if (message.id !== firstUserId) editScrollAnchorRef.current = message.id;
                const accepted = onEditAndResend(message.id, nextDraft);
                if (accepted) {
                  if (message.id === firstUserId) followBottom(true);
                  setEditingMessageId(null);
                }
                else editScrollAnchorRef.current = null;
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
              onArchiveOldChats={onArchiveOld}
              onArchiveOldestChats={onArchiveOldest}
              archivePending={archivePending}
              hfBilling={null}
              openRouterFallbackEnabled={openRouterFallbackEnabled}
              feedbackEnabled
            />)}
      </div>
    </div>
    {!followingBottom && <button
      type="button"
      className="chat-jump-latest"
      onClick={() => {
        followBottom(true);
        const scroller = scrollRef.current;
        if (scroller) {
          scroller.focus({ preventScroll: true });
          scroller.scrollTop = scroller.scrollHeight;
        }
      }}
    >Jump to latest</button>}
    </div>
  );
}

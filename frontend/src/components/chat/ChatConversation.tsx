import { useEffect, useLayoutEffect, useRef, useState } from "react";

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
  onArchiveOld,
  onArchiveOldest,
}: ChatConversationProps) {
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollTopBeforeToggleRef = useRef<number | null>(null);
  const editScrollAnchorRef = useRef<string | null>(null);
  const followingBottomRef = useRef(true);
  const previousUserCountRef = useRef(0);
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
    if (userCount > previousUserCountRef.current) {
      followingBottomRef.current = true;
    }
    previousUserCountRef.current = userCount;
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
        followingBottomRef.current = false;
        return;
      }
    }
    if (followingBottomRef.current) scrollElement.scrollTop = scrollElement.scrollHeight;
  }, [messages, userCount]);

  const toggleBlock = (messageId: string, blockIndex: number) => {
    scrollTopBeforeToggleRef.current = scrollRef.current?.scrollTop ?? null;
    onToggleBlock(messageId, blockIndex);
  };

  return (
    <div
      className="chat-conversation"
      ref={scrollRef}
      onScroll={(event) => {
        const { scrollHeight, scrollTop, clientHeight } = event.currentTarget;
        followingBottomRef.current = scrollHeight - scrollTop - clientHeight <= 48;
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
                  if (message.id === firstUserId) followingBottomRef.current = true;
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
              onArchiveOldChats={onArchiveOld}
              onArchiveOldestChats={onArchiveOldest}
              archivePending={archivePending}
              hfBilling={null}
              openRouterFallbackEnabled={openRouterFallbackEnabled}
              feedbackEnabled
            />)}
      </div>
    </div>
  );
}

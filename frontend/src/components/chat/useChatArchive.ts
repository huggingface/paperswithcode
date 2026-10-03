import { useState } from "react";

import { useToast } from "@/components/ui/use-toast";
import type { ChatDraft, ChatMessage } from "@/lib/chat";
import { archiveOldChats, archiveOldestChats } from "@/lib/chatSessions";

interface UseChatArchiveOptions {
  messages: ChatMessage[];
  refreshSessions: () => Promise<void>;
  resetChat: () => void;
  restoreDraft: (draft: ChatDraft) => void;
}

export function useChatArchive({
  messages,
  refreshSessions,
  resetChat,
  restoreDraft,
}: UseChatArchiveOptions) {
  const { toast } = useToast();
  const [pending, setPending] = useState<"old" | "oldest" | null>(null);

  const restoreQuestion = () => {
    const failedMessage = [...messages].reverse().find(
      (message) => message.role === "user",
    );
    resetChat();
    restoreDraft({
      text: failedMessage?.text ?? "",
      paperMentions: failedMessage?.paperMentions ?? [],
      ...(failedMessage?.paperSelection
        ? { paperSelection: failedMessage.paperSelection }
        : {}),
    });
  };

  const archiveOld = async () => {
    if (pending !== null) return;
    setPending("old");
    try {
      const result = await archiveOldChats();
      await refreshSessions();
      if (result.archived_count === 0) {
        toast({
          title: "No chats were archived",
          description: "There are no inactive chats older than 30 days.",
        });
        return;
      }
      restoreQuestion();
      toast({
        title: `${result.archived_count} ${result.archived_count === 1 ? "chat" : "chats"} archived`,
        description: "Your question is ready to send again.",
      });
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Could not archive old chats",
        description: error instanceof Error ? error.message : "Try again.",
      });
    } finally {
      setPending(null);
    }
  };

  const archiveOldest = async () => {
    if (pending !== null) return;
    setPending("oldest");
    try {
      const result = await archiveOldestChats();
      await refreshSessions();
      restoreQuestion();
      toast({
        title: `${result.archived_count} ${result.archived_count === 1 ? "chat" : "chats"} archived`,
        description: "Your question is ready to send again.",
      });
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Could not archive chats",
        description: error instanceof Error ? error.message : "Try again.",
      });
    } finally {
      setPending(null);
    }
  };

  return { pending, archiveOld, archiveOldest };
}

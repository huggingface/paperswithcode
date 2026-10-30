import { useMutation } from "@tanstack/react-query";

import { useToast } from "@/hooks/use-toast";
import { chatApi } from "@/lib/api/chat";
import { draftFromMessage, latestUserMessage, type ChatDraft, type ChatMessage } from "@/lib/chat";

type ArchiveScope = "old" | "oldest";

interface UseChatArchiveOptions {
  messages: ChatMessage[];
  refreshSessions: () => Promise<void>;
  resetChat: () => void;
  restoreDraft: (draft: ChatDraft) => void;
}

const FAILURE_TITLES: Record<ArchiveScope, string> = {
  old: "Could not archive old chats",
  oldest: "Could not archive chats",
};

export function useChatArchive({
  messages,
  refreshSessions,
  resetChat,
  restoreDraft,
}: UseChatArchiveOptions) {
  const { toast } = useToast();
  const mutation = useMutation({
    mutationFn: async (scope: ArchiveScope) => {
      const result = scope === "old"
        ? await chatApi.archiveOldChats()
        : await chatApi.archiveOldestChats();
      await refreshSessions();
      return result;
    },
    onSuccess: ({ archived_count: count }, scope) => {
      if (scope === "old" && count === 0) {
        toast({
          title: "No chats were archived",
          description: "There are no inactive chats older than 30 days.",
        });
        return;
      }
      // The quota error belongs to the latest question; offer it again.
      const failedMessage = latestUserMessage(messages);
      resetChat();
      restoreDraft(draftFromMessage(failedMessage));
      toast({
        title: `${count} ${count === 1 ? "chat" : "chats"} archived`,
        description: "Your question is ready to send again.",
      });
    },
    onError: (error, scope) => {
      toast({
        variant: "destructive",
        title: FAILURE_TITLES[scope],
        description: error instanceof Error ? error.message : "Try again.",
      });
    },
  });
  const pending: ArchiveScope | null = mutation.isPending ? mutation.variables ?? null : null;

  const archive = async (scope: ArchiveScope) => {
    if (pending !== null) return;
    await mutation.mutateAsync(scope).catch(() => undefined);
  };

  return {
    pending,
    archiveOld: () => archive("old"),
    archiveOldest: () => archive("oldest"),
  };
}

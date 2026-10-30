import { useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { chatApi } from "@/lib/api/chat";
import type { ChatSession, ChatSessionDetail } from "@/lib/api/chat.types";
import { chatSessionKeys } from "@/lib/chatSessionQueries";
import type { ChatTurnConfiguration } from "@/lib/chatTurn";

const DELETE_STOP_TIMEOUT_MS = 3_000;
const DELETE_STOP_POLL_MS = 150;

const errorText = (error: unknown, fallback: string) => (
  error instanceof Error ? error.message : fallback
);

/** The signed-in user's cached chat list and session details. */
export function useChatSessionCache(userId: string | null) {
  const queryClient = useQueryClient();
  const setSessions = useCallback((update: (previous: ChatSession[]) => ChatSession[]) => {
    queryClient.setQueryData<ChatSession[]>(chatSessionKeys.list(userId), (previous) => update(previous ?? []));
  }, [queryClient, userId]);
  const patchSession = useCallback((id: string, patch: Partial<ChatSessionDetail>) => {
    setSessions((previous) => previous.map((session) => session.id === id ? { ...session, ...patch } : session));
    queryClient.setQueryData<ChatSessionDetail>(chatSessionKeys.detail(userId, id), (previous) => (
      previous ? { ...previous, ...patch } : previous
    ));
  }, [queryClient, setSessions, userId]);
  const refreshSessions = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: chatSessionKeys.list(userId) });
  }, [queryClient, userId]);
  /** A turn was admitted: show its session as generating, inserting a new chat first. */
  const markSessionBusy = useCallback((id: string, configuration: Required<ChatTurnConfiguration>) => {
    void queryClient.cancelQueries({ queryKey: chatSessionKeys.list(userId) });
    const now = new Date().toISOString();
    setSessions((previous) => previous.some((session) => session.id === id)
      ? previous.map((session) => session.id === id ? { ...session, is_busy: true } : session)
      : [{
          id,
          title: "New chat",
          selected_model: configuration.model,
          created_at: now,
          updated_at: now,
          message_count: 1,
          is_busy: true,
          web_search_enabled: configuration.webSearchEnabled,
          reasoning_effort: configuration.reasoningEffort,
        }, ...previous]);
  }, [queryClient, setSessions, userId]);
  return { markSessionBusy, patchSession, refreshSessions };
}

interface ChatSessionActionsOptions {
  routeSessionId: string | undefined;
  selectedModel: string;
  setSelectedModel: (model: string) => void;
  patchSession: (id: string, patch: Partial<ChatSessionDetail>) => void;
  /** A user-chosen title wins over titles streamed by the session's turn. */
  onRenamed: (id: string) => void;
  refreshSessions: () => Promise<void>;
  onError: (message: string) => void;
  /** Called after the selected chat was deleted. */
  onSelectedDeleted: () => void;
  /** Whether `id` is generating; it is stopped before deletion. */
  isActive: (id: string) => boolean;
  stopActive: () => void;
}

/** Rename, delete, and model changes for saved conversations. */
export function useChatSessionActions({
  routeSessionId,
  selectedModel,
  setSelectedModel,
  patchSession,
  onRenamed,
  refreshSessions,
  onError,
  onSelectedDeleted,
  isActive,
  stopActive,
}: ChatSessionActionsOptions) {
  const renameMutation = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => chatApi.updateSession(id, { title }),
    onSuccess: (updated, { id }) => {
      onRenamed(id);
      patchSession(id, updated);
    },
    onError: (error) => onError(errorText(error, "Rename failed")),
  });

  const deleteMutation = useMutation({
    mutationFn: async ({ id, active }: { id: string; active: boolean }) => {
      if (active) {
        const deadline = Date.now() + DELETE_STOP_TIMEOUT_MS;
        for (;;) {
          const detail = await chatApi.getSession(id);
          if (!detail.is_busy) break;
          if (Date.now() >= deadline) throw new Error("Generation is still stopping. The chat was not deleted.");
          await new Promise((resolve) => window.setTimeout(resolve, DELETE_STOP_POLL_MS));
        }
      }
      await chatApi.removeSession(id);
      if (id === routeSessionId) onSelectedDeleted();
      await refreshSessions();
    },
    onError: (error) => onError(errorText(error, "Delete failed")),
  });

  const modelMutation = useMutation({
    mutationFn: ({ sessionId, model }: { sessionId: string; model: string; previous: string }) => (
      chatApi.updateSession(sessionId, { selected_model: model })
    ),
    onSuccess: (updated, { sessionId }) => {
      patchSession(sessionId, { selected_model: updated.selected_model });
      onError("");
    },
    onError: (error, { previous }) => {
      setSelectedModel(previous);
      onError(errorText(error, "Model change failed"));
    },
  });

  const rename = (id: string, title: string) => renameMutation.mutateAsync({ id, title }).then(
    () => true,
    () => false,
  );

  const remove = async (id: string) => {
    const active = isActive(id);
    if (!window.confirm(active ? "Stop and delete this chat? This cannot be undone." : "Delete this chat? This cannot be undone.")) return;
    if (active) stopActive();
    await deleteMutation.mutateAsync({ id, active }).catch(() => undefined);
  };

  const changeModel = async (model: string) => {
    const previous = selectedModel;
    setSelectedModel(model);
    if (!routeSessionId) return true;
    return modelMutation.mutateAsync({ sessionId: routeSessionId, model, previous }).then(
      () => true,
      () => false,
    );
  };

  return { rename, remove, changeModel };
}

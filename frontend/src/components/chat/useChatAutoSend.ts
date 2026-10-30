import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";

import type { ChatDraft, PaperSelectionDraft } from "@/lib/chat";
import { forgetStoredChatDraft, readStoredChatDraft } from "@/lib/chatLaunch";
import { emptyChatDraft } from "@/lib/paperSelection";

interface ChatAutoSendOptions {
  /** The prompt waiting to be sent: from `?q=`, a queued launch, or sign-in. */
  pendingDraft: ChatDraft;
  setPendingDraft: (draft: ChatDraft) => void;
  /** True while the prompt cannot be sent yet. */
  blocked: boolean;
  authLoading: boolean;
  signedIn: boolean;
  send: (draft: ChatDraft) => Promise<void>;
  restoreDraft: (draft: ChatDraft) => void;
  setSelectedModel: (model: string) => void;
  onPaperSelectionChange?: (selection?: PaperSelectionDraft) => void;
}

/** Sends a launched or authorized prompt exactly once when the chat is ready. */
export function useChatAutoSend({
  pendingDraft,
  setPendingDraft,
  blocked,
  authLoading,
  signedIn,
  send,
  restoreDraft,
  setSelectedModel,
  onPaperSelectionChange,
}: ChatAutoSendOptions) {
  const [searchParams, setSearchParams] = useSearchParams();
  const startedRef = useRef(false);

  // A prompt kept across sign-in returns to the composer, or auto-sends when queued.
  useEffect(() => {
    if (authLoading || !signedIn) return;
    const stored = readStoredChatDraft();
    if (!stored) return;
    if (stored.draft.paperSelection) onPaperSelectionChange?.(stored.draft.paperSelection);
    if (stored.autoSend) {
      setPendingDraft(stored.draft);
    } else {
      restoreDraft(stored.draft);
      forgetStoredChatDraft();
    }
  }, [authLoading, onPaperSelectionChange, restoreDraft, setPendingDraft, signedIn]);

  useEffect(() => {
    if (authLoading) return;
    const prompt = searchParams.get("q")?.trim();
    if (!prompt) return;
    startedRef.current = false;
    const requestedModel = searchParams.get("model");
    if (requestedModel) setSelectedModel(requestedModel);
    setPendingDraft(emptyChatDraft(prompt));
    const next = new URLSearchParams(searchParams);
    next.delete("q");
    next.delete("model");
    setSearchParams(next, { replace: true });
  }, [authLoading, searchParams, setPendingDraft, setSearchParams, setSelectedModel]);

  useEffect(() => {
    if (blocked || !pendingDraft.text || startedRef.current) return;
    // Deferring avoids React StrictMode's development-only effect cleanup from
    // aborting the request before the second effect pass can own it.
    const timer = window.setTimeout(() => {
      if (startedRef.current) return;
      startedRef.current = true;
      void send(pendingDraft).finally(() => setPendingDraft(emptyChatDraft()));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [blocked, pendingDraft, send, setPendingDraft]);
}

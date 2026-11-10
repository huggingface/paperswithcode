/**
 * Streams dictated text into a chat draft at the caret.
 *
 * The draft and the selection are captured when recording starts; every
 * update rebuilds the draft from that snapshot, so quick successive deltas
 * never read a stale render and paper mentions keep their offsets. The
 * selected text, if any, is replaced. Cancelling restores the snapshot.
 */

import { useQueryClient } from "@tanstack/react-query";
import React from "react";

import { reconcilePaperMentions } from "@/components/chat/usePaperMentions";
import { useDictation } from "@/hooks/useDictation";
import type { ChatDraft } from "@/lib/chat";
import { withDraftText } from "@/lib/paperSelection";

export interface DictationSnapshot {
  draft: ChatDraft;
  start: number;
  end: number;
}

/** Joins dictated text into the snapshot, adding spaces only where needed. */
export function spliceDictation(snapshot: DictationSnapshot, transcript: string): { draft: ChatDraft; caret: number } {
  const before = snapshot.draft.text.slice(0, snapshot.start);
  const after = snapshot.draft.text.slice(snapshot.end);
  let inserted = transcript.replace(/^\s+/, "");
  if (inserted && before && !/\s$/.test(before)) inserted = ` ${inserted}`;
  if (inserted && after && !/^[\s.,;:!?)]/.test(after) && !/\s$/.test(inserted)) inserted = `${inserted} `;
  const text = before + inserted + after;
  const mentions = reconcilePaperMentions(snapshot.draft.text, text, snapshot.draft.paperMentions);
  return { draft: withDraftText(snapshot.draft, text, mentions), caret: before.length + inserted.trimEnd().length };
}

interface UseComposerDictationOptions {
  draft: ChatDraft;
  onChange: (draft: ChatDraft) => void;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  /** Called after the transcript is final (or discarded, when `cancelled`). */
  onEnd?: (cancelled: boolean) => void;
}

export function useComposerDictation({ draft, onChange, textareaRef, onEnd }: UseComposerDictationOptions) {
  const queryClient = useQueryClient();
  const snapshot = React.useRef<DictationSnapshot | null>(null);
  const transcript = React.useRef("");
  const [error, setError] = React.useState("");
  const latest = React.useRef({ draft, onChange, onEnd });
  latest.current = { draft, onChange, onEnd };

  const apply = () => {
    if (!snapshot.current) return;
    const next = spliceDictation(snapshot.current, transcript.current);
    latest.current.onChange(next.draft);
    window.requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.setSelectionRange(next.caret, next.caret);
      el.scrollTop = el.scrollHeight;
    });
  };

  const dictation = useDictation({
    onText: (delta) => {
      transcript.current += delta;
      apply();
    },
    onEnd: ({ cancelled, error: message }) => {
      if (cancelled && snapshot.current) latest.current.onChange(snapshot.current.draft);
      snapshot.current = null;
      transcript.current = "";
      if (message) setError(message);
      void queryClient.invalidateQueries({ queryKey: ["dictationStatus"] });
      latest.current.onEnd?.(cancelled || Boolean(message));
      window.requestAnimationFrame(() => textareaRef.current?.focus());
    },
  });

  const start = () => {
    const el = textareaRef.current;
    const length = latest.current.draft.text.length;
    snapshot.current = {
      draft: latest.current.draft,
      start: el ? el.selectionStart : length,
      end: el ? el.selectionEnd : length,
    };
    transcript.current = "";
    setError("");
    void dictation.start();
  };

  return {
    ...dictation,
    active: dictation.phase !== "idle",
    error,
    clearError: () => setError(""),
    start,
  };
}

import { useQuery } from "@tanstack/react-query";
import React from "react";

import { chatApi } from "@/lib/api/chat";
import type { ChatDraft } from "@/lib/chat";
import { completeChatText } from "@/lib/chatPrompts";

interface CaretState { text: string; atEnd: boolean }

/**
 * Suggests the rest of what the visitor is typing, which Tab accepts. Only
 * offered with the caret at the end of the text and outside a paper mention;
 * text replaced from outside the textarea counts as having the caret at the end.
 */
export function useChatCompletion(draft: ChatDraft, suppressed = false) {
  const text = draft.text;
  const [caret, setCaret] = React.useState<CaretState | null>(null);
  // Fetched once the visitor starts typing, then kept for the page's lifetime.
  const vocabulary = useQuery({
    queryKey: ["chatAutocompleteVocabulary"],
    queryFn: () => chatApi.getAutocompleteVocabulary(),
    enabled: text.length > 0,
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
  });

  const caretAtEnd = caret?.text === text ? caret.atEnd : true;
  const mentionAtEnd = draft.paperMentions.some((mention) => mention.end === text.length);
  const completion = !suppressed && caretAtEnd && !mentionAtEnd
    ? completeChatText(text, vocabulary.data?.names ?? [])
    : "";

  const trackCaret = (element: HTMLTextAreaElement) => setCaret({
    text: element.value,
    atEnd: element.selectionStart === element.selectionEnd && element.selectionEnd === element.value.length,
  });

  return { completion, trackCaret };
}

/**
 * Whether a keydown is a bare Tab, the key that accepts a completion. Tab
 * during IME composition belongs to the input method.
 */
export const isCompletionKey = (event: React.KeyboardEvent) =>
  event.key === "Tab" && !event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey
  && !event.nativeEvent.isComposing;

/**
 * Height that fits the typed text plus its painted completion, which can wrap
 * onto a line the textarea alone would not need. Measure after resetting the
 * textarea's height so the highlight layer can shrink with it.
 */
export const completedScrollHeight = (textarea: HTMLTextAreaElement) => {
  const layer = textarea.parentElement?.querySelector<HTMLElement>(".chat-paper-highlight-layer");
  return Math.max(textarea.scrollHeight, layer?.scrollHeight ?? 0);
};

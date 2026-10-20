import React from "react";

import type { PaperMentionDraft } from "@/lib/chat";

interface PaperMentionHighlightsProps {
  text: string;
  mentions: PaperMentionDraft[];
  scrollTop?: number;
  variant?: "composer" | "editor" | "home";
  // Faint suggested continuation painted after the typed text.
  completion?: string;
}

/**
 * Mirrors textarea wrapping underneath the native control and paints only the
 * selected paper ranges. The textarea remains the sole editable/accessibility
 * surface; this layer is visual and never handles pointer events.
 */
export const PaperMentionHighlights: React.FC<PaperMentionHighlightsProps> = ({
  text,
  mentions,
  scrollTop = 0,
  variant = "composer",
  completion = "",
}) => {
  const pieces: React.ReactNode[] = [];
  let cursor = 0;

  for (const mention of [...mentions].sort((left, right) => left.start - right.start)) {
    const marker = text.slice(mention.start, mention.end);
    const validMarker = marker === mention.title || marker === `@${mention.title}`;
    if (mention.start < cursor || mention.end > text.length || !validMarker) continue;
    pieces.push(text.slice(cursor, mention.start));
    pieces.push(
      <span
        className={`chat-paper-inline-highlight${mention.unavailable ? " is-unavailable" : ""}`}
        data-paper-route-id={mention.route_id}
        key={mention.key}
      >
        {marker}
      </span>,
    );
    cursor = mention.end;
  }

  pieces.push(text.slice(cursor));
  if (completion) {
    pieces.push(<span className="chat-prompt-completion" key="completion">{completion}</span>);
  }
  if (text.endsWith("\n")) pieces.push("\u200b");

  return (
    <div
      aria-hidden="true"
      className={`chat-paper-highlight-layer chat-paper-highlight-layer-${variant}`}
    >
      <div style={{ transform: `translateY(-${scrollTop}px)` }}>{pieces}</div>
    </div>
  );
};

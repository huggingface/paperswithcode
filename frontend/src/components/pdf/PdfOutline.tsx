import { useEffect, useId, useState } from "react";

import type { PdfOutlineEntry } from "./pdfOutline";

interface PdfOutlineProps {
  entries: PdfOutlineEntry[];
  activeIndex: number;
  onSelect: (entry: PdfOutlineEntry) => void;
}

/**
 * Hover table of contents: a rail of one tick per section along the right
 * edge of the PDF, which reveals the full outline while hovered, focused, or
 * toggled open. The rail width tracks the reading position.
 */
export function PdfOutline({ entries, activeIndex, onSelect }: PdfOutlineProps) {
  const panelId = useId();
  const [pinned, setPinned] = useState(false);
  useEffect(() => {
    if (!pinned) return;
    // Capture phase, so Escape closes the panel before the reader's own
    // Escape handling (close search, leave the reader) sees the key.
    const close = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setPinned(false);
    };
    window.addEventListener("keydown", close, { capture: true });
    return () => window.removeEventListener("keydown", close, { capture: true });
  }, [pinned]);
  if (!entries.length) return null;

  return <nav className={`pdf-outline${pinned ? " is-pinned" : ""}`} aria-label="Paper sections">
    <button
      type="button"
      className="pdf-outline-rail"
      aria-label="Table of contents"
      aria-expanded={pinned}
      aria-controls={panelId}
      onClick={() => setPinned((value) => !value)}
    >
      {entries.map((entry) => <span
        key={entry.index}
        className={`pdf-outline-tick level-${entry.level}${entry.index === activeIndex ? " is-active" : ""}`}
      />)}
    </button>
    <div id={panelId} className="pdf-outline-panel">
      <ol>
        {entries.map((entry) => <li key={entry.index} className={`level-${entry.level}`}>
          <a
            href={`#pdf-section-${entry.index}`}
            aria-current={entry.index === activeIndex ? "location" : undefined}
            onClick={(event) => {
              event.preventDefault();
              // Drop focus too, or :focus-within keeps the panel over the heading.
              event.currentTarget.blur();
              setPinned(false);
              onSelect(entry);
            }}
          >{entry.title}</a>
        </li>)}
      </ol>
    </div>
  </nav>;
}

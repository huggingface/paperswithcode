import { useEffect, useId, useRef, useState, type CSSProperties, type PointerEvent } from "react";

import type { PdfOutlineEntry } from "./pdfOutline";

interface PdfOutlineProps {
  entries: PdfOutlineEntry[];
  activeIndex: number;
  onSelect: (entry: PdfOutlineEntry) => void;
}

interface Scrub {
  /** Position of the tick under the pointer. */
  position: number;
  /** Vertical centre of that tick, relative to the outline. */
  top: number;
  /** A finger dragged along the rail: label the tick and jump there on release. */
  dragged: boolean;
}

// Ticks within this many positions of the pointer swell, the nearest most.
const POP_RADIUS = 3;
// A finger must travel this far along the rail before a tap becomes a scrub.
const SCRUB_THRESHOLD = 6;

function nearestTick(rail: HTMLElement, clientY: number) {
  let position = 0;
  let center = 0;
  rail.querySelectorAll<HTMLElement>(".pdf-outline-tick").forEach((tick, index) => {
    const box = tick.getBoundingClientRect();
    const tickCenter = box.top + box.height / 2;
    if (index === 0 || Math.abs(tickCenter - clientY) < Math.abs(center - clientY)) {
      position = index;
      center = tickCenter;
    }
  });
  return { position, center };
}

/**
 * Hover table of contents: a rail of one tick per section along the right
 * edge of the PDF, which reveals the full outline while hovered, focused, or
 * toggled open. The rail width tracks the reading position. Ticks near the
 * pointer swell; dragging a finger along the rail labels the section under it
 * and jumps there on release.
 */
export function PdfOutline({ entries, activeIndex, onSelect }: PdfOutlineProps) {
  const panelId = useId();
  const [pinned, setPinned] = useState(false);
  const [scrub, setScrub] = useState<Scrub | null>(null);
  const touchStart = useRef<number | null>(null);
  const dragged = useRef(false);
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

  const track = (event: PointerEvent<HTMLButtonElement>) => {
    const { position, center } = nearestTick(event.currentTarget, event.clientY);
    const top = center - event.currentTarget.parentElement!.getBoundingClientRect().top;
    setScrub({ position, top, dragged: dragged.current });
  };
  const stopScrub = () => {
    touchStart.current = null;
    setScrub(null);
  };
  const startTouch = (event: PointerEvent<HTMLButtonElement>) => {
    dragged.current = false;
    if (event.pointerType === "mouse") return;
    // Keep receiving moves once the finger slides off the narrow rail.
    event.currentTarget.setPointerCapture?.(event.pointerId);
    touchStart.current = event.clientY;
    track(event);
  };
  const move = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.pointerType !== "mouse") {
      if (touchStart.current === null) return;
      if (Math.abs(event.clientY - touchStart.current) > SCRUB_THRESHOLD) dragged.current = true;
    }
    track(event);
  };
  const endTouch = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.pointerType === "mouse") return;
    if (dragged.current && scrub) {
      setPinned(false);
      onSelect(entries[scrub.position]);
    }
    stopScrub();
  };
  const popOf = (position: number) => scrub
    ? Math.max(0, 1 - Math.abs(position - scrub.position) / POP_RADIUS)
    : 0;
  const label = scrub?.dragged && !pinned ? entries[scrub.position] : null;

  return <nav className={`pdf-outline${pinned ? " is-pinned" : ""}`} aria-label="Paper sections">
    <button
      type="button"
      className="pdf-outline-rail"
      aria-label="Table of contents"
      aria-expanded={pinned}
      aria-controls={panelId}
      onClick={() => {
        // A finger drag already jumped; the click that follows it is not a tap.
        if (dragged.current) {
          dragged.current = false;
          return;
        }
        setPinned((value) => !value);
      }}
      onPointerDown={startTouch}
      onPointerMove={move}
      onPointerUp={endTouch}
      onPointerCancel={() => {
        dragged.current = false;
        stopScrub();
      }}
      onPointerLeave={(event) => {
        if (event.pointerType === "mouse") stopScrub();
      }}
    >
      {entries.map((entry, position) => <span
        key={entry.index}
        className={`pdf-outline-tick level-${entry.level}${entry.index === activeIndex ? " is-active" : ""}${scrub?.position === position ? " is-scrubbed" : ""}`}
        style={{ "--pop": popOf(position) } as CSSProperties}
      />)}
    </button>
    {label && <span className="pdf-outline-scrub-label" style={{ top: scrub!.top }} aria-hidden="true">{label.title}</span>}
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

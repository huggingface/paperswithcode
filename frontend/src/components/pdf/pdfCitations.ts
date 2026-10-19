import type { PaperLayout } from "@/lib/api/papers";

/** One box to highlight, on Chandra's 0-1000 grid of its page. */
export interface PdfHighlightBox {
  page: number;
  bbox: number[];
}

/** A highlight request; a new nonce re-scrolls and replays the flash. */
export interface PdfHighlight {
  boxes: PdfHighlightBox[];
  nonce: number;
}

export const PDF_CITATION_ANCHOR = /^p\d+b\d+$/;

/**
 * The boxes a citation covers: one block, or for a section header the header
 * plus every block that belongs to its section.
 */
export function citationBoxes(layout: PaperLayout, anchor: string): PdfHighlightBox[] {
  const block = layout.blocks[anchor];
  if (!block) return [];
  if (block.label !== "Section-Header") return [{ page: block.page, bbox: block.bbox }];
  return Object.entries(layout.blocks)
    .filter(([key, entry]) => key === anchor || entry.section === anchor)
    .map(([, entry]) => ({ page: entry.page, bbox: entry.bbox }));
}

/** The cited anchors in an answer, in first-citation order. */
export function citedAnchors(text: string): string[] {
  const anchors = [...text.matchAll(/\]\(pdf:(p\d+b\d+)\)/g)].map((match) => match[1]);
  return [...new Set(anchors)];
}

const PREVIEW_MAX_WIDTH = 320;
const VIEWPORT_MARGIN = 12;
// Room the preview needs above the chip before it opens below instead.
const PREVIEW_ROOM_ABOVE = 170;

export interface PreviewPlacement {
  /** Horizontal offset from the chip's left edge, in px. */
  left: number;
  below: boolean;
}

/** Keep the hover preview inside the viewport, whatever the chip's position. */
export function previewPlacement(
  chip: Pick<DOMRect, "left" | "top">,
  viewportWidth: number,
): PreviewPlacement {
  const width = Math.min(PREVIEW_MAX_WIDTH, viewportWidth * 0.7);
  const rightmost = viewportWidth - VIEWPORT_MARGIN - width - chip.left;
  const leftmost = VIEWPORT_MARGIN - chip.left;
  return {
    left: Math.max(leftmost, Math.min(0, rightmost)),
    below: chip.top < PREVIEW_ROOM_ABOVE,
  };
}

/**
 * Sentence-case a citation label: uppercase its first letter, unless the label
 * starts with a deliberately lowercase term such as "pLDDT" or "iPhone".
 */
export function capitalizeCitationLabel(label: string): string {
  const [first, second] = label;
  if (!first || first === first.toUpperCase()) return label;
  if (second && second !== second.toLowerCase()) return label;
  return first.toUpperCase() + label.slice(1);
}

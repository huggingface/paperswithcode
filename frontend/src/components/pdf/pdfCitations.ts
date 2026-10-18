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

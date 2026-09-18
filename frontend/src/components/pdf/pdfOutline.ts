import type { PDFDocumentProxy } from "pdfjs-dist/types/src/display/api";

export interface PdfOutlineEntry {
  /** Stable position in document order; also the `#pdf-section-<index>` anchor. */
  index: number;
  title: string;
  /** Nesting depth, 0 for top-level chapters. */
  level: number;
  /** 1-based page number of the section start. */
  page: number;
  /** Section start as a fraction of the page height from the top (0 = top edge). */
  offset: number;
}

interface OutlineNode {
  title: string;
  dest: string | unknown[] | null;
  items: OutlineNode[];
}

export const PDF_SECTION_HASH = /^#pdf-section-(\d+)$/;
export const MAX_OUTLINE_DEPTH = 2;

/** Section index encoded in a `#pdf-section-<index>` location hash, if any. */
export function pdfSectionFromHash(hash: string): number | undefined {
  const match = PDF_SECTION_HASH.exec(hash);
  return match ? Number(match[1]) : undefined;
}

/**
 * Index of the section the reader is in: the last entry whose start lies at or
 * above the reading anchor. `tops` are section starts in the same coordinate
 * space as `anchor` (viewport pixels), in document order; -1 before the first.
 */
export function activeSectionIndex(tops: number[], anchor: number): number {
  let active = -1;
  tops.forEach((top, index) => {
    if (top <= anchor) active = index;
  });
  return active;
}

type Destination = unknown[];

async function resolveDestination(pdf: PDFDocumentProxy, dest: OutlineNode["dest"]): Promise<Destination | null> {
  if (typeof dest === "string") return pdf.getDestination(dest);
  return Array.isArray(dest) ? dest : null;
}

async function destinationPosition(pdf: PDFDocumentProxy, dest: Destination): Promise<{ page: number; offset: number } | null> {
  const [target, kind, , y] = dest as [unknown, { name?: string } | undefined, unknown, unknown];
  let pageIndex: number;
  if (typeof target === "number") pageIndex = target;
  else if (target && typeof target === "object" && "num" in target) pageIndex = await pdf.getPageIndex(target as { num: number; gen: number });
  else return null;
  if (!Number.isInteger(pageIndex) || pageIndex < 0 || pageIndex >= pdf.numPages) return null;
  const page = pageIndex + 1;
  // Only XYZ destinations carry a vertical anchor; others start at the page top.
  if (kind?.name !== "XYZ" || typeof y !== "number") return { page, offset: 0 };
  const view = (await pdf.getPage(page)).view;
  const [, bottom, , top] = view;
  const height = top - bottom;
  if (!(height > 0)) return { page, offset: 0 };
  return { page, offset: Math.min(1, Math.max(0, (top - y) / height)) };
}

/**
 * Flatten the PDF's embedded outline (its bookmarks) into document-ordered
 * section entries with resolved page positions. Documents without an outline
 * yield an empty list; the reader then shows no table of contents.
 */
export async function loadPdfOutline(pdf: PDFDocumentProxy): Promise<PdfOutlineEntry[]> {
  const nodes = (await pdf.getOutline()) as OutlineNode[] | null;
  const entries: PdfOutlineEntry[] = [];
  const visit = async (items: OutlineNode[], level: number) => {
    for (const node of items) {
      const title = node.title.replace(/\s+/g, " ").trim();
      const dest = await resolveDestination(pdf, node.dest).catch(() => null);
      const position = dest ? await destinationPosition(pdf, dest).catch(() => null) : null;
      if (title && position) entries.push({ index: entries.length, title, level, ...position });
      if (level + 1 < MAX_OUTLINE_DEPTH && node.items?.length) await visit(node.items, level + 1);
    }
  };
  await visit(nodes ?? [], 0);
  return entries;
}

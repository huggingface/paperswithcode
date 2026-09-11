import type { ChatDraft, PaperMentionDraft, PaperSelectionDraft, PaperSelectionWire } from "@/lib/chat";

const PAPER_SELECTION_MAX_CHARS = 8_000;
const PAPER_SELECTION_MAX_BYTES = 16_384;
const PAPER_SELECTION_MAX_PAGE = 10_000;

export const PDF_SELECTION_ERRORS = {
  crossPage: "Select text within one PDF page.",
  outside: "Select text from the paper, not the surrounding interface.",
  tooLarge: "Select a shorter passage (maximum 8,000 characters).",
} as const;

export function paperSelectionUtf8Bytes(text: string): number {
  return new TextEncoder().encode(text).length;
}

export function normalizePaperSelectionText(value: string): string {
  return value
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/\u00a0/g, " ")
    .replace(/[^\S\n]+/g, " ")
    .trim();
}

export function paperSelectionFingerprint(selection: PaperSelectionDraft): string {
  return `${selection.routeId}\0${selection.paperVersion}\0${selection.page}\0${selection.text}`;
}

export function toPaperSelectionWire(selection: PaperSelectionDraft): PaperSelectionWire {
  return {
    route_id: selection.routeId,
    paper_version: selection.paperVersion,
    page: selection.page,
    text: selection.text,
  };
}

export function emptyChatDraft(text = "", paperSelection?: PaperSelectionDraft): ChatDraft {
  return paperSelection
    ? { text, paperMentions: [], paperSelection }
    : { text, paperMentions: [] };
}

export function withDraftText(
  draft: ChatDraft,
  text: string,
  paperMentions: PaperMentionDraft[],
): ChatDraft {
  return draft.paperSelection
    ? { text, paperMentions, paperSelection: draft.paperSelection }
    : { text, paperMentions };
}

export function parsePaperSelectionDraft(value: unknown): PaperSelectionDraft | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  if (typeof record.routeId !== "string" || !record.routeId.trim()) return undefined;
  if (typeof record.paperVersion !== "string" || !record.paperVersion.trim()) return undefined;
  const page = record.page;
  if (typeof page !== "number" || !Number.isInteger(page) || page < 1 || page > PAPER_SELECTION_MAX_PAGE) {
    return undefined;
  }
  if (typeof record.text !== "string") return undefined;
  const text = normalizePaperSelectionText(record.text);
  if (!text) return undefined;
  if (text.length > PAPER_SELECTION_MAX_CHARS) return undefined;
  if (paperSelectionUtf8Bytes(text) > PAPER_SELECTION_MAX_BYTES) return undefined;
  return {
    routeId: record.routeId.trim(),
    paperVersion: record.paperVersion.trim(),
    page,
    text,
  };
}

export function parseChatDraft(raw: unknown, fallbackText?: string): ChatDraft | null {
  if (typeof raw === "string") return emptyChatDraft(raw);
  if (!raw || typeof raw !== "object") {
    return fallbackText === undefined ? null : emptyChatDraft(fallbackText);
  }
  const record = raw as Record<string, unknown>;
  if (typeof record.text !== "string" || !Array.isArray(record.paperMentions)) {
    return fallbackText === undefined ? null : emptyChatDraft(fallbackText);
  }
  const paperSelection = parsePaperSelectionDraft(record.paperSelection);
  return paperSelection
    ? { text: record.text, paperMentions: record.paperMentions as ChatDraft["paperMentions"], paperSelection }
    : { text: record.text, paperMentions: record.paperMentions as ChatDraft["paperMentions"] };
}

export type PdfSelectionCommit =
  | { ok: true; selection: PaperSelectionDraft }
  | { ok: false; error: string | null };

function closestElement(node: Node | null): Element | null {
  if (!node) return null;
  return node instanceof Element ? node : node.parentElement;
}

function pageFromNode(node: Node | null, pagesRoot: Element): number | null {
  const element = closestElement(node);
  if (!element || !pagesRoot.contains(element)) return null;
  if (!element.closest(".textLayer")) return null;
  const pageElement = element.closest<HTMLElement>(".pdf-page[data-page]");
  if (!pageElement || !pagesRoot.contains(pageElement)) return null;
  const page = Number(pageElement.dataset.page);
  if (!Number.isInteger(page) || page < 1 || page > PAPER_SELECTION_MAX_PAGE) return null;
  return page;
}

export function commitPdfSelection(input: {
  selection: Selection | null;
  pagesRoot: Element | null;
  routeId: string;
  paperVersion: string;
  numPages?: number;
}): PdfSelectionCommit {
  const { selection, pagesRoot, routeId, paperVersion, numPages } = input;
  if (!pagesRoot || !selection || selection.rangeCount !== 1) {
    if (selection && selection.rangeCount > 1) {
      return { ok: false, error: PDF_SELECTION_ERRORS.crossPage };
    }
    return { ok: false, error: null };
  }
  const range = selection.getRangeAt(0);
  if (range.collapsed) return { ok: false, error: null };
  const anchorPage = pageFromNode(range.startContainer, pagesRoot);
  const focusPage = pageFromNode(range.endContainer, pagesRoot);
  const ancestor = closestElement(range.commonAncestorContainer);
  if (!ancestor || !pagesRoot.contains(ancestor)) {
    return { ok: false, error: PDF_SELECTION_ERRORS.outside };
  }
  if (anchorPage === null || focusPage === null) {
    return { ok: false, error: PDF_SELECTION_ERRORS.outside };
  }
  if (anchorPage !== focusPage) {
    return { ok: false, error: PDF_SELECTION_ERRORS.crossPage };
  }
  if (numPages && (anchorPage < 1 || anchorPage > numPages)) {
    return { ok: false, error: PDF_SELECTION_ERRORS.crossPage };
  }
  const raw = selection.toString();
  const text = normalizePaperSelectionText(raw);
  if (!text) return { ok: false, error: PDF_SELECTION_ERRORS.crossPage };
  if (text.length > PAPER_SELECTION_MAX_CHARS || paperSelectionUtf8Bytes(text) > PAPER_SELECTION_MAX_BYTES) {
    return { ok: false, error: PDF_SELECTION_ERRORS.tooLarge };
  }
  return {
    ok: true,
    selection: {
      routeId,
      paperVersion,
      page: anchorPage,
      text,
    },
  };
}

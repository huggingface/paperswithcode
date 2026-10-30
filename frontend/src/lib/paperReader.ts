import type { Paper } from "@/lib/api/papers.types";
import { safeExternalHref } from "@/lib/safeExternalHref";

// Venue and publisher landing pages show an abstract, not the paper. Mirrors
// LANDING_PAGE_HOSTS in backend/services/external_page_markdown_service.py.
const LANDING_PAGE_HOSTS = new Set([
  "aclanthology.org",
  "dl.acm.org",
  "doi.org",
  "dx.doi.org",
  "eccv.ecva.net",
  "ieeexplore.ieee.org",
  "link.springer.com",
  "openaccess.thecvf.com",
  "openreview.net",
  "sciencedirect.com",
  "zenodo.org",
]);

function looksLikePdfUrl(value: unknown): boolean {
  const href = safeExternalHref(value);
  if (!href) return false;
  const parsed = new URL(href);
  const marker = `${parsed.pathname}?${parsed.search}`.toLowerCase();
  return marker.includes(".pdf") || parsed.pathname.toLowerCase().includes("/pdf");
}

function hasExternalPdf(paper: Paper): boolean {
  return looksLikePdfUrl(paper.source_url) || Boolean(safeExternalHref(paper.conference_url_pdf));
}

/** The web page an HTML-only external paper is read from, as Markdown. */
export function externalPaperWebPage(paper: Paper): string | null {
  if (paper.source !== "external" || hasExternalPdf(paper)) return null;
  const href = safeExternalHref(paper.source_url);
  if (!href) return null;
  const parsed = new URL(href);
  // A fragment points into a page that lists many papers.
  if (parsed.hash || LANDING_PAGE_HOSTS.has(parsed.hostname.replace(/^www\./, ""))) return null;
  return href;
}

export function paperReaderRoute(paper: Paper, fallbackRoute: string): string | null {
  if (paper.source === "external") {
    const readable = hasExternalPdf(paper) || Boolean(externalPaperWebPage(paper));
    return readable && paper.id ? `/pdf/${paper.id}` : null;
  }
  const route = (paper.arxiv_id || fallbackRoute).replace(/v\d+$/i, "");
  return safeExternalHref(paper.url_pdf) && route ? `/pdf/${route}` : null;
}

// Per-paper reader state in sessionStorage, keyed by the reader route ID.
export const readerSessionKey = (readerId: string) => `pwc:reader:session:${readerId}`;
export const readerCollapsedKey = (readerId: string) => `pwc:reader:assistant-collapsed:${readerId}`;
export const readerPageKey = (readerId: string) => `pwc:reader:page:${readerId}`;

/** Opens the reader on page 1 with a fresh, expanded assistant. */
export function resetReaderSession(readerRoute: string): void {
  const readerId = readerRoute.slice("/pdf/".length);
  sessionStorage.removeItem(readerSessionKey(readerId));
  sessionStorage.removeItem(readerCollapsedKey(readerId));
  sessionStorage.removeItem(readerPageKey(readerId));
}

const CANONICAL_HEADER = /^Title: [^\n]*\n\nURL Source: [^\n]*\n\nMarkdown Content:\n/;

/** A web paper's own Markdown, without the canonical paper-Markdown header. */
export function webPaperBody(markdown: string): string {
  return markdown.replace(CANONICAL_HEADER, "").trim();
}

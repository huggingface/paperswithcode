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

/**
 * The original PDF an external paper is archived from. Mirrors
 * external_pdf_url in .github/workflows/scripts/hourly/backfill_paper_markdown.py.
 */
export function externalPaperPdf(paper: Paper): string | null {
  if (looksLikePdfUrl(paper.source_url)) return safeExternalHref(paper.source_url);
  return safeExternalHref(paper.conference_url_pdf);
}

function hasExternalPdf(paper: Paper): boolean {
  return Boolean(externalPaperPdf(paper));
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

/**
 * Whether a web paper's original page is known to allow framing without
 * asking the server. GitHub Pages cannot send X-Frame-Options or CSP headers;
 * other pages are framed only once the hourly header check allowed them,
 * because a blocked frame renders blank.
 */
export function framesOriginalPage(href: string): boolean {
  const parsed = new URL(href);
  return parsed.protocol === "https:" && parsed.hostname.toLowerCase().endsWith(".github.io");
}

/** Whether two links open the same page, ignoring scheme, `www.`, and a trailing slash. */
export function sameWebPage(left: string, right: string): boolean {
  const key = (href: string) => {
    const parsed = new URL(href);
    return `${parsed.hostname.replace(/^www\./, "")}${parsed.pathname.replace(/\/+$/, "")}${parsed.search}`;
  };
  return key(left) === key(right);
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

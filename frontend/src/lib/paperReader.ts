import type { Paper } from "@/lib/api/papers.types";
import { safeExternalHref } from "@/lib/safeExternalHref";

function looksLikePdfUrl(value: unknown): boolean {
  const href = safeExternalHref(value);
  if (!href) return false;
  const parsed = new URL(href);
  const marker = `${parsed.pathname}?${parsed.search}`.toLowerCase();
  return marker.includes(".pdf") || parsed.pathname.toLowerCase().includes("/pdf");
}

export function paperReaderRoute(paper: Paper, fallbackRoute: string): string | null {
  if (paper.source === "external") {
    const hasPdf = looksLikePdfUrl(paper.source_url)
      || Boolean(safeExternalHref(paper.conference_url_pdf));
    return hasPdf && paper.id ? `/pdf/${paper.id}` : null;
  }
  const route = (paper.arxiv_id || fallbackRoute).replace(/v\d+$/i, "");
  return safeExternalHref(paper.url_pdf) && route ? `/pdf/${route}` : null;
}

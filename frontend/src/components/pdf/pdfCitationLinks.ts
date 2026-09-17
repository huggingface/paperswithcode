import type { PDFDocumentProxy, TextContent } from "pdfjs-dist/types/src/display/api";

export interface PdfLinkAnnotation {
  id: string;
  subtype?: string;
  url?: string;
  dest?: unknown;
  rect?: number[];
}

export function arxivIdFromUrl(value: string): string | null {
  let url: URL;
  try { url = new URL(value); } catch { return null; }
  if (!['http:', 'https:'].includes(url.protocol) || !/^(www\.)?arxiv\.org$/i.test(url.hostname)) return null;
  const match = url.pathname.match(/^\/(?:abs|pdf|html)\/(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?\/\d{7})(?:v\d+)?(?:\.pdf)?\/?$/i);
  return match?.[1] ?? null;
}

interface ReferencePosition { name: string; page: number; x: number; y: number }

// Resolve only explicit PDF links, never guesses from author names. Named
// bibliography destinations delimit the entry containing an external arXiv link.
export function createPdfCitationResolver(pdf: PDFDocumentProxy) {
  let references: Promise<ReferencePosition[]> | undefined;
  const pageLinks = new Map<number, Promise<PdfLinkAnnotation[]>>();
  const pageText = new Map<number, Promise<TextContent>>();
  const citations = new Map<string, Promise<string | null>>();
  const getReferences = () => references ??= (async () => {
    const destinations = await pdf.getDestinations();
    const positions: ReferencePosition[] = [];
    for (const [name, dest] of Object.entries(destinations)) {
      if (!/^cite[.:]/i.test(name) || dest[1]?.name !== 'XYZ' || typeof dest[2] !== 'number' || typeof dest[3] !== 'number') continue;
      const page = typeof dest[0] === 'number' ? dest[0] + 1 : await pdf.getPageIndex(dest[0]) + 1;
      positions.push({ name, page, x: dest[2], y: dest[3] });
    }
    return positions;
  })();
  const resolveCitation = (name: string) => {
    let result = citations.get(name);
    if (!result) {
      result = (async () => {
        const positions = await getReferences();
        const start = positions.find(position => position.name === name);
        if (!start) return null;
        const samePage = positions.filter(position => position.page === start.page);
        const column = samePage.filter(position => Math.abs(position.x - start.x) < 24);
        const bottom = Math.max(0, ...column.filter(position => position.y < start.y - 1).map(position => position.y));
        const right = Math.min(Infinity, ...samePage.filter(position => position.x > start.x + 24).map(position => position.x - 4));
        let annotations = pageLinks.get(start.page);
        if (!annotations) {
          annotations = pdf.getPage(start.page).then(page => page.getAnnotations());
          pageLinks.set(start.page, annotations);
        }
        const ids = new Set<string>();
        const insideEntry = (x: number, y: number) => x >= start.x - 4 && x < right && y <= start.y + 3 && y > bottom;
        for (const annotation of await annotations) {
          if (!annotation.url || !annotation.rect) continue;
          const id = arxivIdFromUrl(annotation.url);
          if (!id) continue;
          const [x1, y1, x2, y2] = annotation.rect;
          const x = (x1 + x2) / 2;
          const y = (y1 + y2) / 2;
          if (insideEntry(x, y)) ids.add(id);
        }
        let text = pageText.get(start.page);
        if (!text) {
          text = pdf.getPage(start.page).then(page => page.getTextContent());
          pageText.set(start.page, text);
        }
        const entry = (await text).items.filter(item => 'str' in item && insideEntry(item.transform[4], item.transform[5]))
          .map(item => 'str' in item ? item.str : '').join('').replace(/\s/g, '');
        // Explicit identifiers only; no title/author fuzzy matching. Joining
        // text items also handles arXiv URLs broken across lines in the PDF.
        for (const match of entry.matchAll(/(?:arxiv:|arxiv\.org\/(?:abs|pdf|html)\/)(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?\/\d{7})(?:v\d+)?/gi)) ids.add(match[1]);
        return ids.size === 1 ? [...ids][0] : null;
      })();
      citations.set(name, result);
    }
    return result;
  };
  return async (annotation: PdfLinkAnnotation): Promise<string | null> => {
    if (annotation.url) return arxivIdFromUrl(annotation.url);
    if (typeof annotation.dest === 'string' && /^cite[.:]/i.test(annotation.dest)) return resolveCitation(annotation.dest);
    return null;
  };
}
export type PdfCitationResolver = ReturnType<typeof createPdfCitationResolver>;

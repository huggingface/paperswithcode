import type { PDFDocumentProxy, TextContent, TextItem } from "pdfjs-dist/types/src/display/api";
import type { PaperReferenceQuery } from "@/lib/api/papers.types";

export interface PdfLinkAnnotation {
  id: string;
  subtype?: string;
  url?: string;
  dest?: unknown;
  rect?: number[];
}

/** Resolves bibliography entries to paper route ids, keyed by destination name. */
export type PdfCitationLookup = (references: PaperReferenceQuery[]) => Promise<Map<string, string>>;

export function arxivIdFromUrl(value: string): string | null {
  let url: URL;
  try { url = new URL(value); } catch { return null; }
  if (!['http:', 'https:'].includes(url.protocol) || !/^(www\.)?arxiv\.org$/i.test(url.hostname)) return null;
  const match = url.pathname.match(/^\/(?:abs|pdf|html)\/(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?\/\d{7})(?:v\d+)?(?:\.pdf)?\/?$/i);
  return match?.[1] ?? null;
}

const MAX_TITLE_CANDIDATES = 8;
const REFERENCE_HEADING_SCAN_PAGES = 12;
const MAX_TITLE_LENGTH = 300;

// Sentences of a bibliography entry that could be its title. The backend only
// accepts an exact letters-and-digits match, so author lists and venues are
// harmless extra candidates; adjacent pairs cover titles containing a period.
export function referenceTitleCandidates(entry: string): string[] {
  const sentences = entry
    .replace(/^\s*\[[^\]]{1,6}\]\s*/, '')
    .split(/[.?!](?=\s|$|[A-Z])/)
    .map(sentence => sentence.replace(/\s+/g, ' ').trim())
    .filter(Boolean);
  const plausible = (sentence: string) =>
    sentence.length <= MAX_TITLE_LENGTH && sentence.split(' ').length >= 3
    && /[a-z]/i.test(sentence) && !/https?:\/\//i.test(sentence) && !/^arxiv preprint/i.test(sentence);
  const byLength = (a: string, b: string) => b.length - a.length;
  const singles = sentences.filter(plausible).sort(byLength);
  const pairs = sentences.slice(0, -1).map((sentence, index) => `${sentence}. ${sentences[index + 1]}`).filter(plausible).sort(byLength);
  return [...new Set([...singles, ...pairs])].slice(0, MAX_TITLE_CANDIDATES);
}

interface ReferencePosition { name: string; page: number; x: number; y: number }
interface TextLine { text: string; x: number; baseline: number }

// Groups text items into printed lines; labels such as "[20]" may arrive split
// across several items.
function textLines(items: TextContent['items']): TextLine[] {
  const lines: TextLine[] = [];
  let current: TextLine | undefined;
  for (const item of items) {
    if (!('str' in item)) continue;
    const y = item.transform[5];
    if (!current || Math.abs(y - current.baseline) > 1) {
      current = { text: '', x: item.transform[4], baseline: y };
      lines.push(current);
    }
    current.text += item.str;
    if (item.hasEOL) current = undefined;
  }
  return lines.map(line => ({ ...line, text: line.text.trim() })).filter(line => line.text);
}
interface ReferenceEntry { arxivId: string | null; titles: string[]; box: number[] | null }
interface PageText { view: number[]; content: TextContent }

/** A resolved bibliography entry on one page; box is [x0, y0, x1, y1] on a 0–1000 page grid. */
export interface PdfBibliographyLink { name: string; routeId: string; box: number[] }

// Named bibliography destinations delimit each entry. An explicit arXiv link or
// identifier inside the entry wins; otherwise the entry's sentences go to the
// catalog for exact title matching. Author names alone never resolve anything.
export function createPdfCitationResolver(pdf: PDFDocumentProxy, lookup?: PdfCitationLookup) {
  let references: Promise<ReferencePosition[]> | undefined;
  const pageLinks = new Map<number, Promise<PdfLinkAnnotation[]>>();
  const pageText = new Map<number, Promise<PageText>>();
  const entries = new Map<string, Promise<ReferenceEntry | null>>();
  let catalog: Promise<Map<string, string>> | undefined;
  const getPageText = (page: number) => {
    let text = pageText.get(page);
    if (!text) {
      text = pdf.getPage(page).then(async proxy => ({ view: proxy.view, content: await proxy.getTextContent() }));
      pageText.set(page, text);
    }
    return text;
  };
  const getReferences = () => references ??= (async () => {
    const destinations = await pdf.getDestinations();
    const positions: ReferencePosition[] = [];
    for (const [name, dest] of Object.entries(destinations)) {
      if (!/^cite[.:]/i.test(name) || dest[1]?.name !== 'XYZ' || typeof dest[2] !== 'number' || typeof dest[3] !== 'number') continue;
      const page = typeof dest[0] === 'number' ? dest[0] + 1 : await pdf.getPageIndex(dest[0]) + 1;
      positions.push({ name, page, x: dest[2], y: dest[3] });
    }
    return positions.length ? positions : numberedReferences();
  })();
  // PDFs without hyperref targets (Word exports, for example) still print a
  // "References" heading followed by "[n]" labels at the start of entry lines.
  const numberedReferences = async () => {
    const lines: (TextLine & { page: number })[] = [];
    for (let page = Math.max(1, pdf.numPages - REFERENCE_HEADING_SCAN_PAGES + 1); page <= pdf.numPages; page++) {
      lines.push(...textLines((await getPageText(page)).content.items).map(line => ({ ...line, page })));
    }
    const headings = lines.flatMap((line, index) => /^(?:[\dIVX]+\.?\s*)?(?:references|bibliography)$/i.test(line.text) ? [index] : []);
    // A running "References" header on continuation pages is followed by
    // labels that do not start near [1]; fall back to the heading before it.
    for (const heading of headings.reverse()) {
      const positions: ReferencePosition[] = [];
      let last = 0;
      for (const line of lines.slice(heading + 1)) {
        const label = Number(line.text.match(/^\[(\d{1,3})\]/)?.[1]);
        // Labels ascend; a skipped number tolerates one the text layer garbled.
        if (!(label > last && label <= last + 3)) continue;
        last = label;
        // The baseline, unlike a hyperref target, leaves no room above the
        // label, so an entry never takes the previous entry's last line.
        positions.push({ name: `text:${label}`, page: line.page, x: line.x, y: line.baseline });
      }
      if (positions.length) return positions;
    }
    return [];
  };
  const getEntry = (name: string) => {
    let entry = entries.get(name);
    if (!entry) {
      entry = (async () => {
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
          if (insideEntry((x1 + x2) / 2, (y1 + y2) / 2)) ids.add(id);
        }
        // Line ends become spaces so sentence boundaries survive; the arXiv
        // scan drops all whitespace to catch identifiers broken across lines.
        const { view, content } = await getPageText(start.page);
        const items = content.items.filter((item): item is TextItem => 'str' in item && insideEntry(item.transform[4], item.transform[5]));
        const entryText = items.map(item => item.str + (item.hasEOL ? ' ' : '')).join('');
        // The last entry of a column runs to the page bottom, so a page footer
        // can fall inside it; the box stops at the first gap wider than a blank line.
        const printed = items.filter(item => item.str.trim())
          .sort((a, b) => b.transform[5] - a.transform[5]);
        const gap = printed.findIndex((item, index) => index > 0
          && printed[index - 1].transform[5] - item.transform[5] > 2.5 * Math.max(Math.abs(item.transform[3]), 1));
        if (gap > 0) printed.length = gap;
        let box: number[] | null = null;
        if (printed.length) {
          const [left, bottomEdge, right, top] = view;
          const x = (value: number) => Math.round((value - left) / (right - left) * 1000);
          const y = (value: number) => Math.round((top - value) / (top - bottomEdge) * 1000);
          box = [
            x(Math.min(...printed.map(item => item.transform[4]))),
            y(Math.max(...printed.map(item => item.transform[5] + item.height))),
            x(Math.max(...printed.map(item => item.transform[4] + item.width))),
            y(Math.min(...printed.map(item => item.transform[5]))) + 3,
          ];
        }
        for (const match of entryText.replace(/\s/g, '').matchAll(/(?:arxiv:|arxiv\.org\/(?:abs|pdf|html)\/)(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?\/\d{7})(?:v\d+)?/gi)) ids.add(match[1]);
        return { arxivId: ids.size === 1 ? [...ids][0] : null, titles: referenceTitleCandidates(entryText), box };
      })();
      entries.set(name, entry);
    }
    return entry;
  };
  const getCatalog = () => catalog ??= (async () => {
    const matches = new Map<string, string>();
    if (!lookup) return matches;
    try {
      const positions = await getReferences();
      const queries: PaperReferenceQuery[] = [];
      for (const position of positions) {
        const entry = await getEntry(position.name);
        if (entry && (entry.arxivId || entry.titles.length)) queries.push({ key: position.name, arxiv_id: entry.arxivId, titles: entry.titles });
      }
      return queries.length ? await lookup(queries) : matches;
    } catch {
      // Offline or unparseable bibliography: explicit arXiv identifiers still work.
      return matches;
    }
  })();
  // Warm every bibliography card as soon as the document opens.
  if (lookup) void getCatalog();
  const routeIdFor = async (name: string) => {
    const entry = await getEntry(name);
    if (!entry) return null;
    return entry.arxivId ?? (await getCatalog()).get(name) ?? null;
  };
  const resolve = async (annotation: PdfLinkAnnotation): Promise<string | null> => {
    if (annotation.url) return arxivIdFromUrl(annotation.url);
    if (typeof annotation.dest !== 'string' || !/^cite[.:]/i.test(annotation.dest)) return null;
    return routeIdFor(annotation.dest);
  };
  // The bibliography entries themselves carry no links; they get their own
  // preview targets from the same entries the in-text citations resolve to.
  const bibliographyLinks = async (page: number): Promise<PdfBibliographyLink[]> => {
    const onPage = (await getReferences()).filter(position => position.page === page);
    const links = await Promise.all(onPage.map(async ({ name }) => {
      const [entry, routeId] = await Promise.all([getEntry(name), routeIdFor(name)]);
      return entry?.box && routeId ? { name, routeId, box: entry.box } : null;
    }));
    return links.filter((link): link is PdfBibliographyLink => link !== null);
  };
  return Object.assign(resolve, { bibliographyLinks });
}
export type PdfCitationResolver = ReturnType<typeof createPdfCitationResolver>;

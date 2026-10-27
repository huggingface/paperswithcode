import type { PDFDocumentProxy, TextContent, TextItem } from "pdfjs-dist/types/src/display/api";
import type { PaperReferenceQuery } from "@/lib/api/papers.types";
import type { PdfHighlightBox } from "./pdfCitations";

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

/**
 * A resolved bibliography entry on one page; box is [x0, y0, x1, y1] on a
 * 0–1000 page grid, and citations are where the text cites it, in reading
 * order, each as the boxes of its one or more printed lines.
 */
export interface PdfBibliographyLink { name: string; routeId: string; box: number[]; citations: PdfHighlightBox[][] }

// Converts PDF user-space coordinates to the 0–1000 grid of a page's view box.
function pageGrid([left, bottom, right, top]: number[]) {
  return {
    x: (value: number) => Math.round((value - left) / (right - left) * 1000),
    y: (value: number) => Math.round((top - value) / (top - bottom) * 1000),
  };
}

// Numbered in-text citations such as "[3]", "[2, 7]", or "[4-6]".
const NUMBERED_CITATION = /\[(\d{1,3}(?:\s*[,;\u2013-]\s*\d{1,3})*)\]/g;

function citedNumbers(group: string): number[] {
  return group.split(/[,;]/).flatMap(part => {
    const [from, to = from] = part.split(/[\u2013-]/).map(Number);
    return to >= from && to - from < 50 ? Array.from({ length: to - from + 1 }, (_, index) => from + index) : [from];
  });
}

// Boxes of the numbered citations printed in text items, keyed by number. Items
// of a line are joined first because "[20]" may arrive as "[" + "20]".
export function numberedCitationBoxes(items: TextContent['items'], view: number[]): Map<number, number[][]> {
  const grid = pageGrid(view);
  const boxes = new Map<number, number[][]>();
  const lines: { text: string; parts: { start: number; item: TextItem }[] }[] = [];
  let line: (typeof lines)[number] | undefined;
  for (const item of items) {
    if (!('str' in item)) continue;
    if (!line || Math.abs(item.transform[5] - line.parts[0].item.transform[5]) > 1) {
      line = { text: '', parts: [] };
      lines.push(line);
    }
    line.parts.push({ start: line.text.length, item });
    line.text += item.str;
    if (item.hasEOL) line = undefined;
  }
  for (const { text, parts } of lines) {
    const partAt = (offset: number) => parts.filter(part => part.start <= offset).pop() ?? parts[0];
    // Character positions inside an item are estimated from its width.
    const xAt = (offset: number) => {
      const { start, item } = partAt(offset);
      return item.transform[4] + item.width * Math.min(1, (offset - start) / Math.max(item.str.length, 1));
    };
    for (const match of text.matchAll(NUMBERED_CITATION)) {
      const index = match.index ?? 0;
      const { item } = partAt(index);
      const baseline = item.transform[5];
      const height = item.height || Math.abs(item.transform[3]);
      const box = [grid.x(xAt(index)), grid.y(baseline + height), grid.x(xAt(index + match[0].length)), grid.y(baseline) + 3];
      for (const number of citedNumbers(match[1])) boxes.set(number, [...boxes.get(number) ?? [], box]);
    }
  }
  return boxes;
}

// Named bibliography destinations delimit each entry. An explicit arXiv link or
// identifier inside the entry wins; otherwise the entry's sentences go to the
// catalog for exact title matching. Author names alone never resolve anything.
export function createPdfCitationResolver(pdf: PDFDocumentProxy, lookup?: PdfCitationLookup) {
  let references: Promise<ReferencePosition[]> | undefined;
  const pageLinks = new Map<number, Promise<PdfLinkAnnotation[]>>();
  const pageText = new Map<number, Promise<PageText>>();
  const entries = new Map<string, Promise<ReferenceEntry | null>>();
  let catalog: Promise<Map<string, string>> | undefined;
  let citations: Promise<Map<string, PdfHighlightBox[][]>> | undefined;
  const getPageText = (page: number) => {
    let text = pageText.get(page);
    if (!text) {
      text = pdf.getPage(page).then(async proxy => ({ view: proxy.view, content: await proxy.getTextContent() }));
      pageText.set(page, text);
    }
    return text;
  };
  const getPageLinks = (page: number) => {
    let annotations = pageLinks.get(page);
    if (!annotations) {
      annotations = pdf.getPage(page).then(proxy => proxy.getAnnotations());
      pageLinks.set(page, annotations);
    }
    return annotations;
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
        const ids = new Set<string>();
        const insideEntry = (x: number, y: number) => x >= start.x - 4 && x < right && y <= start.y + 3 && y > bottom;
        for (const annotation of await getPageLinks(start.page)) {
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
          const { x, y } = pageGrid(view);
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
  // Where the text cites each entry: hyperref links to its destination, or for
  // numbered PDFs without them, "[n]" labels printed before the bibliography.
  const getCitations = () => citations ??= (async () => {
    const byName = new Map<string, PdfHighlightBox[][]>();
    const add = (name: string, page: number, bbox: number[]) => {
      const citations = byName.get(name) ?? [];
      const boxes = citations[citations.length - 1];
      const last = boxes?.[boxes.length - 1];
      // Author/year citations link "Chen et al." and "2017" separately: side
      // by side on one line, or wrapped onto the start of the next, they are
      // one citation.
      if (last?.page === page && Math.abs(last.bbox[1] - bbox[1]) < 5 && bbox[0] >= last.bbox[0] && bbox[0] - last.bbox[2] < 15) {
        last.bbox = [last.bbox[0], Math.min(last.bbox[1], bbox[1]), Math.max(last.bbox[2], bbox[2]), Math.max(last.bbox[3], bbox[3])];
      } else if (last?.page === page && bbox[1] > last.bbox[1] && bbox[1] - last.bbox[3] < 10 && bbox[0] < last.bbox[0]) {
        boxes.push({ page, bbox });
      } else {
        byName.set(name, [...citations, [{ page, bbox }]]);
      }
    };
    const positions = await getReferences();
    if (!positions.length) return byName;
    if (positions[0].name.startsWith('text:')) {
      const first = positions[0];
      for (let page = 1; page <= first.page; page++) {
        const { view, content } = await getPageText(page);
        const items = page < first.page ? content.items : content.items.filter(item => 'str' in item && item.transform[5] > first.y + 1);
        for (const [number, boxes] of numberedCitationBoxes(items, view)) {
          for (const bbox of boxes) add(`text:${number}`, page, bbox);
        }
      }
      return byName;
    }
    for (let page = 1; page <= pdf.numPages; page++) {
      const annotations = await getPageLinks(page);
      if (!annotations.some(annotation => typeof annotation.dest === 'string' && /^cite[.:]/i.test(annotation.dest))) continue;
      const { x, y } = pageGrid((await pdf.getPage(page)).view);
      for (const { dest, rect } of annotations) {
        if (typeof dest !== 'string' || !/^cite[.:]/i.test(dest) || !rect) continue;
        add(dest, page, [x(rect[0]), y(rect[3]), x(rect[2]), y(rect[1])]);
      }
    }
    return byName;
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
    if (!onPage.length) return [];
    const cited = await getCitations().catch(() => new Map<string, PdfHighlightBox[][]>());
    const links = await Promise.all(onPage.map(async ({ name }) => {
      const [entry, routeId] = await Promise.all([getEntry(name), routeIdFor(name)]);
      return entry?.box && routeId ? { name, routeId, box: entry.box, citations: cited.get(name) ?? [] } : null;
    }));
    return links.filter((link): link is PdfBibliographyLink => link !== null);
  };
  return Object.assign(resolve, { bibliographyLinks });
}
export type PdfCitationResolver = ReturnType<typeof createPdfCitationResolver>;

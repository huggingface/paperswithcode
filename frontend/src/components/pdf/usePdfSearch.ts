import { useCallback, useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist/types/src/display/api";

import { countMatches, createPdfTextIndex, type PdfTextIndex } from "./pdfTextIndex";

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character] ?? character);
}

export function highlightPdfText(text: string, query: string, active: boolean): string {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return escapeHtml(text);
  const haystack = text.toLocaleLowerCase();
  const className = `pdf-search-highlight${active ? " is-active" : ""}`;
  let cursor = 0;
  let match = haystack.indexOf(needle);
  if (match < 0) return escapeHtml(text);
  let result = "";
  while (match >= 0) {
    result += escapeHtml(text.slice(cursor, match));
    result += `<mark class="${className}">${escapeHtml(text.slice(match, match + needle.length))}</mark>`;
    cursor = match + needle.length;
    match = haystack.indexOf(needle, cursor);
  }
  return result + escapeHtml(text.slice(cursor));
}

export type PdfSearch = ReturnType<typeof usePdfSearch>;

/** Find-in-document over the loaded PDF's text; `jumpToPage` shows a match. */
export function usePdfSearch(pages: number, jumpToPage: (page: number) => void) {
  const textIndex = useRef<PdfTextIndex>();
  const searchGeneration = useRef(0);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  // The query whose matches are shown, so highlights follow the results rather
  // than redrawing every page's text layer on each keystroke.
  const [highlightQuery, setHighlightQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [matches, setMatches] = useState<number[]>([]);
  const [activeMatch, setActiveMatch] = useState(0);

  const indexDocument = useCallback((pdf: PDFDocumentProxy) => {
    textIndex.current = createPdfTextIndex(pdf);
  }, []);

  const close = useCallback(() => {
    searchGeneration.current += 1;
    setOpen(false);
    setQuery("");
    setHighlightQuery("");
    setMatches([]);
    setActiveMatch(0);
    setSearching(false);
  }, []);

  // Extract the document's text as soon as search opens, so the first query
  // does not wait for every page to be fetched and parsed.
  useEffect(() => {
    const index = textIndex.current;
    if (!open || !index) return;
    const indexedPages = index.pages();
    void (async () => {
      while (textIndex.current === index && !(await indexedPages.next()).done);
    })().catch(() => undefined);
  }, [pages, open]);

  useEffect(() => {
    const index = textIndex.current;
    const needle = query.trim().toLocaleLowerCase();
    const generation = ++searchGeneration.current;
    if (!index || !needle) {
      setHighlightQuery("");
      setMatches([]);
      setActiveMatch(0);
      setSearching(false);
      return;
    }
    setSearching(true);
    const timer = window.setTimeout(() => void (async () => {
      setHighlightQuery(query.trim());
      setMatches([]);
      setActiveMatch(0);
      // Publish matches page by page, so the first hit is shown while later
      // pages are still being read.
      const found: number[] = [];
      for await (const [pageNumber, text] of index.pages()) {
        if (searchGeneration.current !== generation) return;
        const count = countMatches(text, needle);
        if (!count) continue;
        if (!found.length) jumpToPage(pageNumber);
        for (let match = 0; match < count; match += 1) found.push(pageNumber);
        setMatches([...found]);
      }
      if (searchGeneration.current === generation) setSearching(false);
    })().catch(() => {
      if (searchGeneration.current === generation) setSearching(false);
    }), 120);
    return () => window.clearTimeout(timer);
    // jumpToPage deliberately reads the current mounted scroll surface.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, pages]);

  const navigate = (direction: 1 | -1) => {
    if (!matches.length) return;
    const next = (activeMatch + direction + matches.length) % matches.length;
    setActiveMatch(next);
    jumpToPage(matches[next]);
  };

  return {
    open,
    setOpen,
    query,
    setQuery,
    highlightQuery,
    searching,
    matches,
    activeMatch,
    close,
    navigate,
    indexDocument,
  };
}

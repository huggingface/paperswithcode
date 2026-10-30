import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Document, type DocumentProps } from "react-pdf";
import type { PDFDocumentProxy } from "pdfjs-dist/types/src/display/api";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";

import { assertPdfWorkerConfigured } from "@/lib/pdf";
import type { PaperSelectionDraft } from "@/lib/chat";
import { usePdfSelection } from "@/hooks/usePdfSelection";
import { createPaperPreviewCache } from "@/components/paper-preview/paperPreviewCache";
import { createPdfCitationResolver, type PdfCitationResolver } from "./pdfCitationLinks";
import type { PdfPaperAuthor } from "./PdfAuthorLink";
import { PdfOutline } from "./PdfOutline";
import { PdfCitationSteps } from "./PdfCitationSteps";
import { LazyPdfPage } from "./PdfPage";
import { activeSectionIndex, loadPdfOutline, pdfSectionFromHash, type PdfOutlineEntry } from "./pdfOutline";
import type { PdfHighlight, PdfHighlightBox } from "./pdfCitations";
import { usePdfSearch, type PdfSearch } from "./usePdfSearch";
import { usePdfZoom } from "./usePdfZoom";

/** What a toolbar shows and drives. */
export interface PdfViewerControls {
  page: number;
  pages: number;
  zoom: number;
  search: PdfSearch;
  onPage: (page: number) => void;
  onZoom: (next: (zoom: number) => number) => void;
}

export interface PdfDocumentViewProps {
  url: string;
  downloadUrl: string;
  paperKey: string;
  initialPage: number;
  resizeActive: boolean;
  selectionEnabled: boolean;
  paperVersion: string;
  documentOptions: DocumentProps["options"];
  label: string;
  loadingLabel: string;
  toolbar: (controls: PdfViewerControls) => ReactNode;
  onRetry: () => void;
  onPaperSelection?: (selection: PaperSelectionDraft) => void;
  onPaperSelectionError?: (message: string) => void;
  onPageChange?: (page: number) => void;
  onClose?: () => void;
  loadErrorMessage?: string;
  /** Passage a chat citation points at: scrolled into view and briefly highlighted. */
  highlight?: PdfHighlight;
  /** Opens preview cards from in-text citations and bibliography entries. */
  citationLinks?: boolean;
  /** Mirrors section jumps in `#pdf-section-<n>` and opens such deep links. */
  sectionHash?: boolean;
  /** The paper's authors; their names on the first page open author cards. */
  authors?: PdfPaperAuthor[];
}

// Section jumps leave this much of the previous section visible above the
// heading; the reading anchor sits just below so the jumped-to section is active.
const SECTION_SCROLL_MARGIN = 8;
const SECTION_ANCHOR_OFFSET = 24;
// Citation jumps keep this much context visible above the highlighted passage.
const CITATION_SCROLL_MARGIN = 72;
// Placeholder height for pages that have not rendered yet, until the document's
// own page proportions are known. Accurate placeholders keep page and section
// jumps from overshooting when the pages above the target are still unrendered.
const DEFAULT_PAGE_ASPECT = 1.35;

function pdfErrorMessage(error: Error): string {
  const message = error.message.toLowerCase();
  if (message.includes("password")) return "This PDF is encrypted and cannot be opened in the reader.";
  if (message.includes("worker")) return "The PDF renderer could not start.";
  if (message.includes("invalid") || message.includes("format")) return "The source returned an invalid or unsupported PDF.";
  if (message.includes("cors") || message.includes("fetch") || message.includes("network")) return "The PDF source could not be loaded in this browser.";
  return "The PDF could not be loaded from its source.";
}

function jumpBehavior(): ScrollBehavior {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth";
}

/** One load of one PDF; remount it to load another document or retry. */
export function PdfDocumentView({
  url,
  downloadUrl,
  paperKey,
  initialPage,
  resizeActive,
  selectionEnabled,
  paperVersion,
  documentOptions,
  label,
  loadingLabel,
  toolbar,
  onRetry,
  onPaperSelection,
  onPaperSelectionError,
  onPageChange,
  onClose,
  loadErrorMessage,
  highlight: citedHighlight,
  citationLinks = false,
  sectionHash = false,
  authors,
}: PdfDocumentViewProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pagesRef = useRef<HTMLDivElement>(null);
  // Preview cards' jumps between in-text citations and bibliography entries
  // reuse the chat citation highlight, flashed more briefly; whichever was
  // requested last is shown.
  const [citationJump, setCitationJump] = useState<PdfHighlight>();
  // The citations of the bibliography entry last jumped from, and which one is shown.
  const [citationSteps, setCitationSteps] = useState<{ citations: PdfHighlightBox[][]; index: number }>();
  useEffect(() => {
    setCitationJump(undefined);
    setCitationSteps(undefined);
  }, [citedHighlight?.nonce, url]);
  const highlight = citationJump ?? citedHighlight;
  const highlightKey = highlight && `${citationJump ? "jump" : "cited"}-${highlight.nonce}`;
  // A card jump's short flash waits for the scroll to land, which can cross
  // many pages; chat citations' longer flash starts at once.
  const [landedKey, setLandedKey] = useState<string>();
  const shownHighlight = citationJump && landedKey !== highlightKey ? undefined : highlight;
  const showCitation = useCallback((citation: PdfHighlightBox[]) => {
    setCitationJump((previous) => ({ boxes: citation, nonce: (previous?.nonce ?? 0) + 1 }));
  }, []);
  const showCitations = useCallback((citations: PdfHighlightBox[][]) => {
    setCitationSteps({ citations, index: 0 });
    showCitation(citations[0]);
  }, [showCitation]);
  const citationStepsOpen = Boolean(citationSteps && citationSteps.citations.length > 1);
  const stepCitation = (direction: 1 | -1) => {
    if (!citationSteps) return;
    const { citations } = citationSteps;
    const index = (citationSteps.index + direction + citations.length) % citations.length;
    setCitationSteps({ citations, index });
    showCitation(citations[index]);
  };
  const documentRef = useRef<PDFDocumentProxy | null>(null);
  const [resolveCitation, setResolveCitation] = useState<PdfCitationResolver>();
  const showReference = useCallback(async (dest: string) => {
    const reference = await resolveCitation?.referenceOf(dest).catch(() => null);
    if (reference) showCitation([reference]);
    return Boolean(reference);
  }, [resolveCitation, showCitation]);
  const queryClient = useQueryClient();
  const previewCache = useMemo(() => createPaperPreviewCache(queryClient), [queryClient]);
  const internalLinkNavigation = useRef<(page: number) => void>(() => {});
  const sectionNavigation = useRef<(entry: PdfOutlineEntry, behavior?: ScrollBehavior) => void>(() => {});
  const [pages, setPages] = useState(0);
  const [pageAspect, setPageAspect] = useState(DEFAULT_PAGE_ASPECT);
  const [outline, setOutline] = useState<PdfOutlineEntry[]>([]);
  const [activeSection, setActiveSection] = useState(-1);
  const [navigationSection, setNavigationSection] = useState<number>();
  const [page, setPage] = useState(initialPage);
  const [navigationPage, setNavigationPage] = useState<number>();
  const [error, setError] = useState("");
  const { zoom, pageWidth, liveResizeScale, setZoom } = usePdfZoom(scrollRef, pagesRef, resizeActive);

  usePdfSelection({
    enabled: selectionEnabled && Boolean(paperVersion),
    pagesRoot: pagesRef,
    routeId: paperKey,
    paperVersion,
    numPages: pages || undefined,
    onSelect: onPaperSelection,
    onError: onPaperSelectionError,
  });

  useEffect(() => {
    assertPdfWorkerConfigured();
  }, []);

  const setCurrentPage = useCallback((next: number) => {
    const bounded = Math.max(1, Math.min(pages || 1, next));
    setPage(bounded);
    onPageChange?.(bounded);
  }, [onPageChange, pages]);

  const jumpToPage = (next: number) => {
    const bounded = Math.max(1, Math.min(pages || 1, next));
    const behavior = jumpBehavior();
    setNavigationPage(behavior === "smooth" ? bounded : undefined);
    scrollRef.current?.querySelector<HTMLElement>(`[data-page="${bounded}"]`)?.scrollIntoView({ block: "start", behavior });
    if (behavior === "instant") setCurrentPage(bounded);
  };
  const search = usePdfSearch(pages, jumpToPage);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element || !pages) return;
    let frame = 0;
    let settleTimer = 0;
    const update = (settled = false) => {
      window.clearTimeout(settleTimer);
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const top = element.getBoundingClientRect().top;
        const center = top + element.clientHeight / 2;
        let bestPage = page;
        let bestDistance = Number.POSITIVE_INFINITY;
        const rects = new Map<number, DOMRect>();
        element.querySelectorAll<HTMLElement>("[data-page]").forEach((candidate) => {
          const rect = candidate.getBoundingClientRect();
          rects.set(Number(candidate.dataset.page), rect);
          const distance = center >= rect.top && center <= rect.bottom
            ? 0
            : Math.min(Math.abs(center - rect.top), Math.abs(center - rect.bottom));
          if (distance < bestDistance) {
            bestDistance = distance;
            bestPage = Number(candidate.dataset.page);
          }
        });
        if (settled) {
          setNavigationPage(undefined);
          setNavigationSection(undefined);
        }
        if (bestPage !== page) setCurrentPage(bestPage);
        // The section in view is the last one starting above the reading
        // anchor, just below the top edge, where section jumps land.
        const sectionTops = outline.map((entry) => {
          const rect = rects.get(entry.page);
          return rect ? rect.top + rect.height * entry.offset : Number.POSITIVE_INFINITY;
        });
        setActiveSection(activeSectionIndex(sectionTops, top + SECTION_ANCHOR_OFFSET));
      });
    };
    // Persist the visible page after scrolling settles, including browsers
    // without scrollend support. Intermediate animation pages are not reading positions.
    const scheduleUpdate = () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout(() => update(true), 150);
    };
    const finishScroll = () => update(true);
    element.addEventListener("scroll", scheduleUpdate, { passive: true });
    element.addEventListener("scrollend", finishScroll);
    update();
    return () => {
      element.removeEventListener("scroll", scheduleUpdate);
      element.removeEventListener("scrollend", finishScroll);
      window.clearTimeout(settleTimer);
      cancelAnimationFrame(frame);
    };
  }, [outline, page, pageWidth, pages, setCurrentPage]);

  const { open: searchOpen, setOpen: setSearchOpen, close: closeSearch } = search;
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") {
        event.preventDefault();
        setSearchOpen(true);
      } else if (event.key === "Escape" && searchOpen) {
        event.preventDefault();
        closeSearch();
      } else if (event.key === "Escape" && citationStepsOpen) {
        event.preventDefault();
        setCitationSteps(undefined);
      } else if (event.key === "Escape" && !event.repeat && onClose) {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [citationStepsOpen, closeSearch, onClose, searchOpen, setSearchOpen]);

  // Scroll so the cited passage sits near the top once the document is laid
  // out; placeholder pages have accurate heights, so the offset holds.
  useEffect(() => {
    const first = highlight?.boxes[0];
    const scroller = scrollRef.current;
    const target = first && scroller?.querySelector<HTMLElement>(`[data-page="${first.page}"]`);
    if (!first || !scroller || !target) return;
    const behavior = jumpBehavior();
    const rect = target.getBoundingClientRect();
    const top = rect.top - scroller.getBoundingClientRect().top + scroller.scrollTop + rect.height * first.bbox[1] / 1000;
    setNavigationPage(behavior === "smooth" ? first.page : undefined);
    scroller.scrollTo({ top: Math.max(0, top - CITATION_SCROLL_MARGIN), behavior });
    if (behavior === "instant") setCurrentPage(first.page);
    // Landed once scrolling settles, as for the reading position, including
    // browsers without scrollend and jumps that need no scroll.
    let settleTimer = 0;
    const land = () => {
      window.clearTimeout(settleTimer);
      setLandedKey(highlightKey);
    };
    const settle = () => {
      window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout(land, 150);
    };
    settle();
    scroller.addEventListener("scroll", settle, { passive: true });
    scroller.addEventListener("scrollend", land);
    return () => {
      window.clearTimeout(settleTimer);
      scroller.removeEventListener("scroll", settle);
      scroller.removeEventListener("scrollend", land);
    };
    // Re-run per request, once pages exist and once the real page aspect is
    // measured (placeholder heights change then), not on scroll-state changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightKey, pages, pageAspect]);
  const jumpToSection = (entry: PdfOutlineEntry, behavior: ScrollBehavior = jumpBehavior()) => {
    const scroller = scrollRef.current;
    const target = scroller?.querySelector<HTMLElement>(`[data-page="${entry.page}"]`);
    if (!scroller || !target) return;
    const rect = target.getBoundingClientRect();
    const top = rect.top - scroller.getBoundingClientRect().top + scroller.scrollTop + rect.height * entry.offset;
    setNavigationPage(behavior === "smooth" ? entry.page : undefined);
    setNavigationSection(behavior === "smooth" ? entry.index : undefined);
    scroller.scrollTo({ top: Math.max(0, top - SECTION_SCROLL_MARGIN), behavior });
    if (behavior === "instant") setCurrentPage(entry.page);
    if (sectionHash) window.history.replaceState(window.history.state, "", `#pdf-section-${entry.index}`);
  };
  // React-PDF retains its initial onItemClick callback. Forward through a ref so
  // links use the loaded page count and current reader callbacks. Our wrappers
  // exist even when the destination Page is unmounted by lazy rendering.
  useLayoutEffect(() => {
    internalLinkNavigation.current = jumpToPage;
    sectionNavigation.current = jumpToSection;
  });
  const pageNumbers = useMemo(() => Array.from({ length: pages }, (_, index) => index + 1), [pages]);

  const loadDocument = (pdf: PDFDocumentProxy) => {
    documentRef.current = pdf;
    search.indexDocument(pdf);
    if (citationLinks) setResolveCitation(() => createPdfCitationResolver(pdf, previewCache.lookup));
    setPages(pdf.numPages);
    setError("");
    // Papers use one page size throughout; the first page stands for all
    // placeholders. If it cannot be read, keep the default proportions and
    // still restore the reader's position.
    const placeholdersSized = pdf.getPage(1).then((first) => {
      const [left, bottom, right, top] = first.view;
      const aspect = (top - bottom) / (right - left);
      if (documentRef.current === pdf && aspect > 0) setPageAspect(aspect);
    }, () => undefined);
    const restoredPage = Math.max(1, Math.min(pdf.numPages, initialPage));
    const restorePage = () => {
      if (restoredPage <= 1) return;
      scrollRef.current?.querySelector<HTMLElement>(`[data-page="${restoredPage}"]`)?.scrollIntoView({ block: "start" });
      setPage(restoredPage);
      onPageChange?.(restoredPage);
    };
    // Scroll only once placeholders have their final size and are laid out,
    // otherwise a later resize would move the target out from under the reader.
    const afterLayout = (callback: () => void) => void placeholdersSized.then(() => {
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (documentRef.current === pdf) callback();
      }));
    });
    // A `#pdf-section-<n>` deep link takes precedence over the remembered
    // page, but only once the outline confirms the section exists.
    const section = sectionHash ? pdfSectionFromHash(window.location.hash) : undefined;
    if (section === undefined) afterLayout(restorePage);
    // A malformed outline must not take the reader down with it.
    void loadPdfOutline(pdf).catch(() => []).then((entries) => {
      if (documentRef.current !== pdf) return;
      setOutline(entries);
      if (section === undefined) return;
      const entry = entries[section];
      afterLayout(() => entry ? sectionNavigation.current(entry, "instant") : restorePage());
    });
  };

  return <div className="pdf-viewer">
    {toolbar({ page: navigationPage ?? page, pages, zoom, search, onPage: jumpToPage, onZoom: setZoom })}
    <div className="pdf-scroll-frame">
    <div ref={scrollRef} className="pdf-scroll" role="region" aria-label={label}>
      {error ? <div className="pdf-error" role="alert">
        <p>{error}</p>
        <div><button type="button" onClick={onRetry}>Retry</button> <a href={downloadUrl} target="_blank" rel="noopener noreferrer">Open PDF</a></div>
      </div> : <Document
        file={url}
        options={documentOptions}
        loading={<div className="pdf-loading" role="status">{loadingLabel}</div>}
        onLoadSuccess={loadDocument}
        onLoadError={(loadError) => setError(loadErrorMessage || pdfErrorMessage(loadError))}
        externalLinkTarget="_blank"
        onItemClick={({ pageNumber }) => internalLinkNavigation.current(pageNumber)}
      >
        <div
          ref={pagesRef}
          className="pdf-pages"
          style={{ "--pdf-live-scale": liveResizeScale.current } as CSSProperties}
        >
          {pageNumbers.map((pageNumber) => <LazyPdfPage
            key={pageNumber}
            page={pageNumber}
            width={pageWidth}
            aspect={pageAspect}
            searchQuery={search.highlightQuery}
            activeSearchPage={search.matches[search.activeMatch]}
            resolveCitation={resolveCitation}
            warmPreviews={previewCache.warm}
            highlightBoxes={shownHighlight?.boxes.filter((box) => box.page === pageNumber).map((box) => box.bbox)}
            highlightKey={highlightKey}
            highlightBrief={Boolean(citationJump)}
            onShowCitations={showCitations}
            onShowReference={showReference}
            authors={pageNumber === 1 ? authors : undefined}
          />)}
        </div>
      </Document>}
    </div>
    {citationSteps && citationStepsOpen && <PdfCitationSteps
      index={citationSteps.index}
      count={citationSteps.citations.length}
      onStep={stepCitation}
      onClose={() => setCitationSteps(undefined)}
    />}
    <PdfOutline
      entries={outline}
      activeIndex={navigationSection ?? activeSection}
      onSelect={jumpToSection}
    />
    </div>
  </div>;
}

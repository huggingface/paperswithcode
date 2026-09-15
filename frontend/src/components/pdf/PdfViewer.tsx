import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import { Document, Page } from "react-pdf";
import type { PDFDocumentProxy, TextItem } from "pdfjs-dist/types/src/display/api";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";

import { assertPdfWorkerConfigured } from "@/lib/pdf";
import type { PaperSelectionDraft } from "@/lib/chat";
import { usePdfSelection } from "@/hooks/usePdfSelection";
import { PdfToolbar } from "./PdfToolbar";
import type { PdfToolbarResources } from "./PdfToolbar";

interface PdfViewerProps {
  url: string;
  downloadUrl?: string;
  paperKey: string;
  paperTitle: string;
  paperHref: string;
  resources?: PdfToolbarResources;
  initialPage?: number;
  resizeActive?: boolean;
  selectionEnabled?: boolean;
  paperVersion?: string;
  onPaperSelection?: (selection: PaperSelectionDraft) => void;
  onPaperSelectionError?: (message: string) => void;
  onPageChange?: (page: number) => void;
  onClose?: () => void;
  loadErrorMessage?: string;
  chrome?: "reader" | "canvas";
}

function pdfErrorMessage(error: Error): string {
  const message = error.message.toLowerCase();
  if (message.includes("password")) return "This PDF is encrypted and cannot be opened in the reader.";
  if (message.includes("worker")) return "The PDF renderer could not start.";
  if (message.includes("invalid") || message.includes("format")) return "The source returned an invalid or unsupported PDF.";
  if (message.includes("cors") || message.includes("fetch") || message.includes("network")) return "The PDF source could not be loaded in this browser.";
  return "The PDF could not be loaded from its source.";
}

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

function LazyPdfPage({
  page,
  width,
  searchQuery,
  activeSearchPage,
}: {
  page: number;
  width: number;
  searchQuery: string;
  activeSearchPage?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(page <= 2);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), {
      rootMargin: "120% 0px",
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return <div ref={ref} className="pdf-page" data-page={page} style={{ minHeight: Math.round(width * 1.35) }}>
    {visible && <Page
      pageNumber={page}
      width={width}
      devicePixelRatio={Math.min(window.devicePixelRatio || 1, 2)}
      renderTextLayer
      renderAnnotationLayer
      loading={null}
      customTextRenderer={searchQuery
        ? ({ str }) => highlightPdfText(str, searchQuery, page === activeSearchPage)
        : undefined}
    />}
  </div>;
}

function CanvasPdfToolbar({
  downloadUrl, page, pages, zoomPercent, onPage, onZoomIn, onZoomOut, onFitWidth,
}: {
  downloadUrl: string;
  page: number;
  pages: number;
  zoomPercent: number;
  onPage: (page: number) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitWidth: () => void;
}) {
  const submitPage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const next = Number(new FormData(event.currentTarget).get("page"));
    if (Number.isInteger(next)) onPage(next);
  };

  return <div className="paper-pdf-toolbar" aria-label="Paper preview controls">
    <div className="paper-pdf-toolbar-group">
      <button type="button" onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="Previous page">Previous</button>
      <form onSubmit={submitPage}>
        <label className="sr-only" htmlFor="paper-pdf-current-page">Current page</label>
        <input id="paper-pdf-current-page" name="page" type="number" min={1} max={pages || 1} defaultValue={page} key={page} aria-label={`Page ${page} of ${pages || "unknown"}`} />
      </form>
      <span role="status" aria-live="polite">Page {page} of {pages || "—"}</span>
      <button type="button" onClick={() => onPage(page + 1)} disabled={!pages || page >= pages} aria-label="Next page">Next</button>
    </div>
    <div className="paper-pdf-toolbar-group">
      <button type="button" onClick={onZoomOut} aria-label="Zoom out">−</button>
      <output aria-live="polite">{zoomPercent}%</output>
      <button type="button" onClick={onZoomIn} aria-label="Zoom in">+</button>
      <button type="button" onClick={onFitWidth}>Fit to width</button>
      <a href={downloadUrl} download>Download PDF</a>
    </div>
  </div>;
}

export function PdfViewer({
  url,
  downloadUrl = url,
  paperKey,
  paperTitle,
  paperHref,
  resources,
  initialPage = 1,
  resizeActive = false,
  selectionEnabled = false,
  paperVersion = "",
  onPaperSelection,
  onPaperSelectionError,
  onPageChange,
  onClose,
  loadErrorMessage,
  chrome = "reader",
}: PdfViewerProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pagesRef = useRef<HTMLDivElement>(null);
  const documentRef = useRef<PDFDocumentProxy | null>(null);
  const internalLinkNavigation = useRef<(page: number) => void>(() => {});
  const searchGeneration = useRef(0);
  const recenterAfterZoom = useRef(false);
  const pinchDelta = useRef(0);
  const pinchFrame = useRef(0);
  const pinchCommitTimer = useRef(0);
  const renderedZoom = useRef(1);
  const liveZoom = useRef(1);
  const liveResizeScale = useRef(1);
  const retainLiveResizeScale = useRef(false);
  const [retry, setRetry] = useState(0);
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(initialPage);
  const [fitWidth, setFitWidth] = useState(700);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [matches, setMatches] = useState<number[]>([]);
  const [activeMatch, setActiveMatch] = useState(0);
  const pageWidth = Math.max(240, Math.round(fitWidth * zoom));
  // Canvas previews are private artifact endpoints. Public reader PDFs must keep
  // their normal cross-origin fetch behavior.
  const documentOptions = useMemo(
    () => chrome === "canvas" ? { withCredentials: true } : undefined,
    [chrome],
  );

  usePdfSelection({
    enabled: selectionEnabled && Boolean(paperVersion),
    pagesRoot: pagesRef,
    routeId: paperKey,
    paperVersion,
    numPages: pages || undefined,
    resetKey: `${paperKey}-${retry}`,
    onSelect: onPaperSelection,
    onError: onPaperSelectionError,
  });

  useEffect(() => {
    assertPdfWorkerConfigured();
  }, []);

  useEffect(() => {
    cancelAnimationFrame(pinchFrame.current);
    window.clearTimeout(pinchCommitTimer.current);
    pinchFrame.current = 0;
    pinchCommitTimer.current = 0;
    pinchDelta.current = 0;
    setPages(0);
    setPage(initialPage);
    setZoom(1);
    renderedZoom.current = 1;
    liveZoom.current = 1;
    liveResizeScale.current = 1;
    retainLiveResizeScale.current = false;
    pagesRef.current?.style.setProperty("--pdf-live-scale", "1");
    setError("");
    setSearchQuery("");
    setMatches([]);
  }, [initialPage, paperKey, retry]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const update = () => {
      const nextWidth = Math.max(240, element.clientWidth - 10);
      if (resizeActive) retainLiveResizeScale.current = true;
      const preserveRenderedPages = resizeActive || retainLiveResizeScale.current;
      liveResizeScale.current = preserveRenderedPages ? nextWidth / fitWidth : 1;
      pagesRef.current?.style.setProperty("--pdf-live-scale", String(liveResizeScale.current));
      if (!preserveRenderedPages) setFitWidth(nextWidth);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [fitWidth, resizeActive]);

  useLayoutEffect(() => {
    renderedZoom.current = zoom;
    pagesRef.current?.style.setProperty(
      "--pdf-live-scale",
      String(retainLiveResizeScale.current ? liveResizeScale.current : 1),
    );
    if (!recenterAfterZoom.current) return;
    const element = scrollRef.current;
    if (element) {
      element.scrollLeft = Math.max(0, (element.scrollWidth - element.clientWidth) / 2);
    }
    recenterAfterZoom.current = false;
  }, [pageWidth, resizeActive, zoom]);

  const setCenteredZoom = useCallback((nextZoom: (value: number) => number) => {
    window.clearTimeout(pinchCommitTimer.current);
    const current = liveZoom.current;
    const next = nextZoom(current);
    liveZoom.current = next;
    recenterAfterZoom.current = next !== renderedZoom.current;
    setZoom(next);
  }, []);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const handlePinch = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      pinchDelta.current += event.deltaY;
      if (pinchFrame.current) return;
      pinchFrame.current = requestAnimationFrame(() => {
        const delta = pinchDelta.current;
        pinchDelta.current = 0;
        pinchFrame.current = 0;
        const next = Math.max(0.5, Math.min(3, liveZoom.current * Math.exp(-delta * 0.002)));
        liveZoom.current = next;
        pagesRef.current?.style.setProperty(
          "--pdf-live-scale",
          String(liveResizeScale.current * next / renderedZoom.current),
        );
        window.clearTimeout(pinchCommitTimer.current);
        pinchCommitTimer.current = window.setTimeout(() => {
          recenterAfterZoom.current = next !== renderedZoom.current;
          setZoom(liveZoom.current);
        }, 180);
      });
    };
    element.addEventListener("wheel", handlePinch, { passive: false });
    return () => {
      element.removeEventListener("wheel", handlePinch);
      cancelAnimationFrame(pinchFrame.current);
      window.clearTimeout(pinchCommitTimer.current);
      pinchFrame.current = 0;
      pinchCommitTimer.current = 0;
      pinchDelta.current = 0;
    };
  }, []);

  const setCurrentPage = useCallback((next: number) => {
    const bounded = Math.max(1, Math.min(pages || 1, next));
    setPage(bounded);
    onPageChange?.(bounded);
  }, [onPageChange, pages]);

  const closeSearch = useCallback(() => {
    searchGeneration.current += 1;
    setSearchOpen(false);
    setSearchQuery("");
    setMatches([]);
    setActiveMatch(0);
    setSearching(false);
  }, []);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element || !pages) return;
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const center = element.getBoundingClientRect().top + element.clientHeight / 2;
        let bestPage = page;
        let bestDistance = Number.POSITIVE_INFINITY;
        element.querySelectorAll<HTMLElement>("[data-page]").forEach((candidate) => {
          const rect = candidate.getBoundingClientRect();
          const distance = center >= rect.top && center <= rect.bottom
            ? 0
            : Math.min(Math.abs(center - rect.top), Math.abs(center - rect.bottom));
          if (distance < bestDistance) {
            bestDistance = distance;
            bestPage = Number(candidate.dataset.page);
          }
        });
        if (bestPage !== page) setCurrentPage(bestPage);
      });
    };
    element.addEventListener("scroll", update, { passive: true });
    update();
    return () => {
      element.removeEventListener("scroll", update);
      cancelAnimationFrame(frame);
    };
  }, [page, pageWidth, pages, setCurrentPage]);

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") {
        event.preventDefault();
        setSearchOpen(true);
      } else if (event.key === "Escape" && searchOpen) {
        event.preventDefault();
        closeSearch();
      } else if (event.key === "Escape" && !event.repeat && onClose) {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [closeSearch, onClose, searchOpen]);

  useEffect(() => {
    const pdf = documentRef.current;
    const query = searchQuery.trim().toLocaleLowerCase();
    const generation = ++searchGeneration.current;
    if (!pdf || !query) {
      setMatches([]);
      setActiveMatch(0);
      setSearching(false);
      return;
    }
    setSearching(true);
    const timer = window.setTimeout(() => void (async () => {
      const found: number[] = [];
      for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
        if (searchGeneration.current !== generation) return;
        const pdfPage = await pdf.getPage(pageNumber);
        const content = await pdfPage.getTextContent();
        const text = content.items.map((item) => "str" in item ? (item as TextItem).str : "").join(" ").toLocaleLowerCase();
        let offset = 0;
        while ((offset = text.indexOf(query, offset)) >= 0) {
          found.push(pageNumber);
          offset += Math.max(1, query.length);
        }
      }
      if (searchGeneration.current === generation) {
        setMatches(found);
        setActiveMatch(0);
        setSearching(false);
        if (found[0]) jumpToPage(found[0]);
      }
    })().catch(() => {
      if (searchGeneration.current === generation) setSearching(false);
    }), 180);
    return () => window.clearTimeout(timer);
    // jumpToPage deliberately reads the current mounted scroll surface.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, pages]);

  const jumpToPage = (next: number) => {
    const bounded = Math.max(1, Math.min(pages || 1, next));
    scrollRef.current?.querySelector<HTMLElement>(`[data-page="${bounded}"]`)?.scrollIntoView({ block: "start" });
    setCurrentPage(bounded);
  };
  // React-PDF retains its initial onItemClick callback. Forward through a ref so
  // links use the loaded page count and current reader callbacks. Our wrappers
  // exist even when the destination Page is unmounted by lazy rendering.
  useLayoutEffect(() => {
    internalLinkNavigation.current = jumpToPage;
  });
  const navigateMatch = (direction: 1 | -1) => {
    if (!matches.length) return;
    const next = (activeMatch + direction + matches.length) % matches.length;
    setActiveMatch(next);
    jumpToPage(matches[next]);
  };
  const pageNumbers = useMemo(() => Array.from({ length: pages }, (_, index) => index + 1), [pages]);

  return <div ref={rootRef} className="pdf-viewer">
    {chrome === "canvas" ? <CanvasPdfToolbar
      downloadUrl={downloadUrl}
      page={page}
      pages={pages}
      zoomPercent={Math.round(zoom * 100)}
      onPage={jumpToPage}
      onZoomIn={() => setCenteredZoom((value) => Math.min(3, value + 0.15))}
      onZoomOut={() => setCenteredZoom((value) => Math.max(0.5, value - 0.15))}
      onFitWidth={() => setCenteredZoom(() => 1)}
    /> : <PdfToolbar
      paperTitle={paperTitle}
      paperHref={paperHref}
      resources={resources}
      page={page}
      pages={pages}
      zoomPercent={Math.round(zoom * 100)}
      searchOpen={searchOpen}
      searchQuery={searchQuery}
      searchMatch={activeMatch}
      searchCount={matches.length}
      searching={searching}
      onPage={jumpToPage}
      onZoomIn={() => setCenteredZoom((value) => Math.min(3, value + 0.15))}
      onZoomOut={() => setCenteredZoom((value) => Math.max(0.5, value - 0.15))}
      onToggleSearch={() => searchOpen ? closeSearch() : setSearchOpen(true)}
      onCloseSearch={closeSearch}
      onSearchQuery={setSearchQuery}
      onSearch={navigateMatch}
    />}
    <div ref={scrollRef} className="pdf-scroll" role="region" aria-label={chrome === "canvas" ? `${paperTitle} PDF preview` : "Paper PDF"}>
      {error ? <div className="pdf-error" role="alert">
        <p>{error}</p>
        <div><button type="button" onClick={() => setRetry((value) => value + 1)}>Retry</button> <a href={url} target="_blank" rel="noopener noreferrer">Open PDF</a></div>
      </div> : <Document
        key={`${paperKey}-${retry}`}
        file={url}
        options={documentOptions}
        loading={<div className="pdf-loading" role="status">{chrome === "canvas" ? "Loading paper preview…" : "Loading paper…"}</div>}
        onLoadSuccess={(pdf) => {
          documentRef.current = pdf;
          setPages(pdf.numPages);
          setError("");
          const restoredPage = Math.max(1, Math.min(pdf.numPages, initialPage));
          if (restoredPage > 1) {
            requestAnimationFrame(() => requestAnimationFrame(() => {
              scrollRef.current?.querySelector<HTMLElement>(`[data-page="${restoredPage}"]`)?.scrollIntoView({ block: "start" });
              setPage(restoredPage);
              onPageChange?.(restoredPage);
            }));
          }
        }}
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
            searchQuery={searchQuery.trim()}
            activeSearchPage={matches[activeMatch]}
          />)}
        </div>
      </Document>}
    </div>
  </div>;
}

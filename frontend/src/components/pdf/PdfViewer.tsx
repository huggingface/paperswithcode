import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Document, Page } from "react-pdf";
import type { PDFDocumentProxy } from "pdfjs-dist/types/src/display/api";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";

import { assertPdfWorkerConfigured } from "@/lib/pdf";
import type { PaperSelectionDraft } from "@/lib/chat";
import { usePdfSelection } from "@/hooks/usePdfSelection";
import { createPaperPreviewCache } from "@/components/paper-preview/paperPreviewCache";
import { PdfToolbar } from "./PdfToolbar";
import type { PdfToolbarResources } from "./PdfToolbar";
import { createPdfCitationResolver, type PdfBibliographyLink, type PdfCitationResolver } from "./pdfCitationLinks";
import { PdfBibliographyEntryLink, PdfPaperLink } from "./PdfPaperLink";
import { PdfAuthorLink, type PdfPaperAuthor } from "./PdfAuthorLink";
import { pdfAuthorBoxes, type PdfAuthorBox } from "./pdfAuthorLinks";
import { usePdfPaperLinks } from "./usePdfPaperLinks";
import { PdfOutline } from "./PdfOutline";
import { PdfCitationSteps } from "./PdfCitationSteps";
import { clampZoom, stepZoom } from "./pdfZoom";
import { activeSectionIndex, loadPdfOutline, pdfSectionFromHash, type PdfOutlineEntry } from "./pdfOutline";
import type { PdfHighlight, PdfHighlightBox } from "./pdfCitations";
import { countMatches, createPdfTextIndex, type PdfTextIndex } from "./pdfTextIndex";

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
  /** Passage a chat citation points at: scrolled into view and briefly highlighted. */
  highlight?: PdfHighlight;
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
// Keep each page canvas within mobile browsers' canvas area limits at high zoom.
const MAX_CANVAS_PIXELS = 16_000_000;

function pageRenderRatio(width: number, aspect: number): number {
  const maxRatio = Math.sqrt(MAX_CANVAS_PIXELS / (width * width * aspect));
  return Math.min(window.devicePixelRatio || 1, 2, maxRatio);
}

interface ZoomAnchor {
  page: HTMLElement;
  fraction: number;
  viewportOffset: number;
}

// Zooming keeps the document point under the anchor (the pointer, or the
// viewport center) in place instead of drifting with the growing pages above it.
function captureZoomAnchor(scroller: HTMLElement, clientY?: number): ZoomAnchor | undefined {
  const top = scroller.getBoundingClientRect().top;
  const anchorY = clientY ?? top + scroller.clientHeight / 2;
  for (const page of scroller.querySelectorAll<HTMLElement>("[data-page]")) {
    const rect = page.getBoundingClientRect();
    if (rect.bottom < anchorY) continue;
    const fraction = rect.height ? Math.max(0, (anchorY - rect.top) / rect.height) : 0;
    return { page, fraction, viewportOffset: anchorY - top };
  }
  return undefined;
}

function restoreZoomAnchor(scroller: HTMLElement, anchor: ZoomAnchor) {
  const rect = anchor.page.getBoundingClientRect();
  const anchorY = scroller.getBoundingClientRect().top + anchor.viewportOffset;
  scroller.scrollTop += rect.top + rect.height * anchor.fraction - anchorY;
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
  aspect,
  searchQuery,
  activeSearchPage,
  resolveCitation,
  warmPreviews,
  highlightBoxes,
  highlightKey,
  highlightBrief,
  onShowCitations,
  onShowReference,
  authors,
}: {
  page: number;
  width: number;
  aspect: number;
  searchQuery: string;
  activeSearchPage?: number;
  resolveCitation?: PdfCitationResolver;
  warmPreviews?: (routeIds: string[]) => void;
  highlightBoxes?: number[][];
  highlightKey?: string;
  highlightBrief?: boolean;
  onShowCitations?: (citations: PdfHighlightBox[][]) => void;
  onShowReference?: (dest: string) => Promise<boolean>;
  authors?: PdfPaperAuthor[];
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(page <= 2);
  const { paperLinks, onAnnotations } = usePdfPaperLinks(ref, visible, resolveCitation, warmPreviews);
  const [bibliographyLinks, setBibliographyLinks] = useState<(PdfBibliographyLink & { citations?: PdfHighlightBox[][] })[]>([]);
  useEffect(() => {
    if (!visible || !resolveCitation) return;
    let current = true;
    void resolveCitation.bibliographyLinks(page).then(async links => {
      if (!current) return;
      if (links.length) warmPreviews?.([...new Set(links.map(link => link.routeId))]);
      setBibliographyLinks(links);
      if (!links.length) return;
      // Cards appear first; their jumps to in-text citations follow the scan.
      const citations = await Promise.all(links.map(link => resolveCitation.citationsOf(link.name)));
      if (current) setBibliographyLinks(links.map((link, index) => ({ ...link, citations: citations[index] })));
    }).catch(() => undefined);
    return () => { current = false; };
  }, [page, resolveCitation, visible, warmPreviews]);
  // A new renderer makes react-pdf rebuild the text layer, so it changes only
  // with the highlighted query, not on every reader re-render.
  const activeSearch = page === activeSearchPage;
  const renderSearchText = useMemo(
    () => searchQuery ? ({ str }: { str: string }) => highlightPdfText(str, searchQuery, activeSearch) : undefined,
    [activeSearch, searchQuery],
  );
  // Double-buffer zoom changes: the last rendered canvas stays on screen,
  // scaled to the new width, while a hidden canvas renders at full resolution.
  // It replaces the old one only once painted, so zooming never blanks a page.
  const [shownWidth, setShownWidth] = useState(width);
  if (!visible && shownWidth !== width) setShownWidth(width);
  // Author names are found in the shown text layer each time it renders, and
  // again when the author list arrives after it.
  // The callback must keep its identity: react-pdf rebuilds the text layer
  // whenever it changes.
  const [textLayerRenders, setTextLayerRenders] = useState(0);
  const textLayerRendered = useCallback(() => setTextLayerRenders((count) => count + 1), []);
  const [authorBoxes, setAuthorBoxes] = useState<PdfAuthorBox[]>([]);
  // Boxes are page fractions, so they stay valid through a zoom until the new
  // text layer replaces them.
  useEffect(() => {
    if (!authors?.length) return setAuthorBoxes([]);
    const layer = ref.current?.querySelector(".pdf-page-layer:not(.is-pending)");
    if (layer?.querySelector(".textLayer")) setAuthorBoxes(pdfAuthorBoxes(layer, authors));
  }, [authors, textLayerRenders]);
  const layerWidths = shownWidth === width ? [width] : [shownWidth, width];
  // A remounted canvas is blank until pdf.js repaints it, so the page's last
  // render stays on top as an image until the fresh canvas has painted.
  const [snapshot, setSnapshot] = useState<string>();
  const [painted, setPainted] = useState(false);
  if (!visible && painted) setPainted(false);
  const snapshotUrl = useRef<string>();
  // Encoding is asynchronous: only the latest capture of a mounted page may
  // publish its image, and each replaced or unmounted image is revoked.
  const latestCapture = useRef(0);
  const capture = useCallback((layerWidth: number) => {
    setPainted(true);
    const id = ++latestCapture.current;
    const canvas = ref.current?.querySelector<HTMLCanvasElement>(`[data-layer-width="${layerWidth}"] canvas`);
    canvas?.toBlob((blob) => {
      if (!blob || id !== latestCapture.current) return;
      if (snapshotUrl.current) URL.revokeObjectURL(snapshotUrl.current);
      snapshotUrl.current = URL.createObjectURL(blob);
      setSnapshot(snapshotUrl.current);
    }, "image/webp", 0.9);
  }, []);
  useEffect(() => () => {
    latestCapture.current += 1;
    if (snapshotUrl.current) URL.revokeObjectURL(snapshotUrl.current);
  }, []);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    // Render well ahead of the viewport so fast scrolling meets painted pages,
    // and release canvases only once they are much farther away, so pages near
    // the reading position are not re-rendered on every change of direction.
    // The margins must extend the scroll container: it clips its pages, so
    // margins around the browser viewport would never see them early.
    const root = element.closest(".pdf-scroll");
    const mount = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) setVisible(true);
    }, { root, rootMargin: "250% 0px" });
    const release = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) setVisible(false);
    }, { root, rootMargin: "600% 0px" });
    mount.observe(element);
    release.observe(element);
    return () => {
      mount.disconnect();
      release.disconnect();
    };
  }, []);
  return <div ref={ref} className="pdf-page" data-page={page} style={{ minHeight: Math.round(width * aspect) }}>
    {visible && layerWidths.map((layerWidth) => {
      const shown = layerWidth === shownWidth;
      const rendered = shown
        ? () => capture(layerWidth)
        : () => {
          setShownWidth(layerWidth);
          capture(layerWidth);
        };
      return <div
        key={layerWidth}
        data-layer-width={layerWidth}
        className={shown ? "pdf-page-layer" : "pdf-page-layer is-pending"}
        style={shown && layerWidth !== width ? { "--pdf-layer-scale": width / layerWidth } as CSSProperties : undefined}
        aria-hidden={shown ? undefined : true}
      >
        <Page
          pageNumber={page}
          width={layerWidth}
          devicePixelRatio={pageRenderRatio(layerWidth, aspect)}
          renderTextLayer={shown}
          renderAnnotationLayer={shown}
          onGetAnnotationsSuccess={onAnnotations}
          onRenderSuccess={rendered}
          onRenderError={shown ? undefined : () => setShownWidth(layerWidth)}
          onRenderTextLayerSuccess={shown && authors ? textLayerRendered : undefined}
          loading={null}
          customTextRenderer={renderSearchText}
        />
      </div>;
    })}
    {snapshot && !painted && <img className="pdf-page-snapshot" src={snapshot} alt="" aria-hidden="true" />}
    {visible && paperLinks.map(link => <PdfPaperLink key={link.anchor.parentElement?.dataset.annotationId} {...link} onShowReference={onShowReference} />)}
    {visible && resolveCitation && bibliographyLinks.map(link => <PdfBibliographyEntryLink key={link.name} {...link} onShowCitations={onShowCitations} />)}
    {visible && authors && authorBoxes.map(({ authorId, box }) => {
      const author = authors.find((candidate) => candidate.id === authorId);
      return author && <PdfAuthorLink key={`${authorId}-${box.join(",")}`} {...author} box={box} />;
    })}
    {highlightBoxes?.map(([x0, y0, x1, y1], index) => <div
      key={`${highlightKey}-${index}`}
      className={`pdf-citation-highlight${highlightBrief ? " is-brief" : ""}`}
      aria-hidden="true"
      style={{ left: `${x0 / 10}%`, top: `${y0 / 10}%`, width: `${(x1 - x0) / 10}%`, height: `${(y1 - y0) / 10}%` }}
    />)}
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
  highlight: citedHighlight,
  authors,
}: PdfViewerProps) {
  const rootRef = useRef<HTMLDivElement>(null);
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
  const textIndex = useRef<PdfTextIndex>();
  const [resolveCitation, setResolveCitation] = useState<PdfCitationResolver>();
  const showReference = useCallback(async (dest: string) => {
    const reference = await resolveCitation?.referenceOf(dest).catch(() => null);
    if (reference) showCitation([reference]);
    return Boolean(reference);
  }, [resolveCitation, showCitation]);
  const queryClient = useQueryClient();
  const previewCache = useMemo(() => createPaperPreviewCache(queryClient), [queryClient]);
  const internalLinkNavigation = useRef<(page: number) => void>(() => {});
  const searchGeneration = useRef(0);
  const recenterAfterZoom = useRef(false);
  const zoomAnchor = useRef<ZoomAnchor>();
  const pinchDelta = useRef(0);
  const pinchClientY = useRef<number>();
  const pinchFrame = useRef(0);
  const pinchCommitTimer = useRef(0);
  const renderedZoom = useRef(1);
  const liveZoom = useRef(1);
  const liveResizeScale = useRef(1);
  const [retry, setRetry] = useState(0);
  const [pages, setPages] = useState(0);
  const [pageAspect, setPageAspect] = useState(DEFAULT_PAGE_ASPECT);
  const [outline, setOutline] = useState<PdfOutlineEntry[]>([]);
  const [activeSection, setActiveSection] = useState(-1);
  const [navigationSection, setNavigationSection] = useState<number>();
  const sectionNavigation = useRef<(entry: PdfOutlineEntry, behavior?: ScrollBehavior) => void>(() => {});
  const [page, setPage] = useState(initialPage);
  const [navigationPage, setNavigationPage] = useState<number>();
  const [fitWidth, setFitWidth] = useState(700);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  // The query whose matches are shown, so highlights follow the results rather
  // than redrawing every page's text layer on each keystroke.
  const [highlightQuery, setHighlightQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [matches, setMatches] = useState<number[]>([]);
  const [activeMatch, setActiveMatch] = useState(0);
  const pageWidth = Math.max(120, Math.round(fitWidth * zoom));
  // Canvas previews are private artifact endpoints. Public reader PDFs must keep
  // their normal cross-origin fetch behavior, and fetch only the byte ranges
  // that visible pages, search, and citations need when the server allows it.
  const documentOptions = useMemo(
    () => chrome === "canvas"
      ? { withCredentials: true }
      : { disableStream: true, disableAutoFetch: true },
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
    setPageAspect(DEFAULT_PAGE_ASPECT);
    setOutline([]);
    setActiveSection(-1);
    setNavigationSection(undefined);
    setResolveCitation(undefined);
    setPage(initialPage);
    setNavigationPage(undefined);
    setZoom(1);
    renderedZoom.current = 1;
    liveZoom.current = 1;
    liveResizeScale.current = 1;
    pagesRef.current?.style.setProperty("--pdf-live-scale", "1");
    setError("");
    textIndex.current = undefined;
    setSearchQuery("");
    setHighlightQuery("");
    setMatches([]);
  }, [initialPage, paperKey, retry]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const update = () => {
      const nextWidth = Math.max(240, element.clientWidth - 10);
      // While the divider or chat toggle moves, the rendered pages only scale.
      // Once it settles, the new width is committed: each page keeps its last
      // canvas scaled until a sharp one at the new width has painted, and the
      // live scale returns to 1 in the same commit.
      liveResizeScale.current = resizeActive ? nextWidth / fitWidth : 1;
      if (resizeActive) {
        pagesRef.current?.style.setProperty("--pdf-live-scale", String(liveResizeScale.current));
      } else {
        setFitWidth(nextWidth);
      }
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [fitWidth, resizeActive]);

  useLayoutEffect(() => {
    renderedZoom.current = zoom;
    pagesRef.current?.style.setProperty("--pdf-live-scale", String(liveResizeScale.current));
    const element = scrollRef.current;
    if (element && zoomAnchor.current) restoreZoomAnchor(element, zoomAnchor.current);
    zoomAnchor.current = undefined;
    if (!recenterAfterZoom.current) return;
    if (element) {
      element.scrollLeft = Math.max(0, (element.scrollWidth - element.clientWidth) / 2);
    }
    recenterAfterZoom.current = false;
  }, [pageWidth, resizeActive, zoom]);

  const setCenteredZoom = useCallback((nextZoom: (value: number) => number) => {
    window.clearTimeout(pinchCommitTimer.current);
    const next = clampZoom(nextZoom(liveZoom.current));
    liveZoom.current = next;
    recenterAfterZoom.current = next !== renderedZoom.current;
    if (recenterAfterZoom.current && scrollRef.current) zoomAnchor.current = captureZoomAnchor(scrollRef.current);
    setZoom(next);
  }, []);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const handlePinch = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      pinchDelta.current += event.deltaY;
      pinchClientY.current = event.clientY;
      if (pinchFrame.current) return;
      pinchFrame.current = requestAnimationFrame(() => {
        const delta = pinchDelta.current;
        pinchDelta.current = 0;
        pinchFrame.current = 0;
        const next = clampZoom(liveZoom.current * Math.exp(-delta * 0.002));
        liveZoom.current = next;
        const anchor = captureZoomAnchor(element, pinchClientY.current);
        pagesRef.current?.style.setProperty(
          "--pdf-live-scale",
          String(liveResizeScale.current * next / renderedZoom.current),
        );
        if (anchor) restoreZoomAnchor(element, anchor);
        window.clearTimeout(pinchCommitTimer.current);
        pinchCommitTimer.current = window.setTimeout(() => {
          recenterAfterZoom.current = next !== renderedZoom.current;
          if (recenterAfterZoom.current) zoomAnchor.current = captureZoomAnchor(element, pinchClientY.current);
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
    setHighlightQuery("");
    setMatches([]);
    setActiveMatch(0);
    setSearching(false);
  }, []);

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
  }, [citationStepsOpen, closeSearch, onClose, searchOpen]);

  // Extract the document's text as soon as search opens, so the first query
  // does not wait for every page to be fetched and parsed.
  useEffect(() => {
    const index = textIndex.current;
    if (!searchOpen || !index) return;
    const pages = index.pages();
    void (async () => {
      while (textIndex.current === index && !(await pages.next()).done);
    })().catch(() => undefined);
  }, [pages, searchOpen]);

  useEffect(() => {
    const index = textIndex.current;
    const query = searchQuery.trim().toLocaleLowerCase();
    const generation = ++searchGeneration.current;
    if (!index || !query) {
      setHighlightQuery("");
      setMatches([]);
      setActiveMatch(0);
      setSearching(false);
      return;
    }
    setSearching(true);
    const timer = window.setTimeout(() => void (async () => {
      setHighlightQuery(searchQuery.trim());
      setMatches([]);
      setActiveMatch(0);
      // Publish matches page by page, so the first hit is shown while later
      // pages are still being read.
      const found: number[] = [];
      for await (const [pageNumber, text] of index.pages()) {
        if (searchGeneration.current !== generation) return;
        const count = countMatches(text, query);
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
  }, [searchQuery, pages]);

  const jumpToPage = (next: number) => {
    const bounded = Math.max(1, Math.min(pages || 1, next));
    const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth";
    setNavigationPage(behavior === "smooth" ? bounded : undefined);
    scrollRef.current?.querySelector<HTMLElement>(`[data-page="${bounded}"]`)?.scrollIntoView({ block: "start", behavior });
    if (behavior === "instant") setCurrentPage(bounded);
  };
  // Scroll so the cited passage sits near the top once the document is laid
  // out; placeholder pages have accurate heights, so the offset holds.
  useEffect(() => {
    const first = highlight?.boxes[0];
    const scroller = scrollRef.current;
    const target = first && scroller?.querySelector<HTMLElement>(`[data-page="${first.page}"]`);
    if (!first || !scroller || !target) return;
    const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth";
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
  const jumpToSection = (entry: PdfOutlineEntry, behavior?: ScrollBehavior) => {
    const scroller = scrollRef.current;
    const target = scroller?.querySelector<HTMLElement>(`[data-page="${entry.page}"]`);
    if (!scroller || !target) return;
    const resolvedBehavior = behavior
      ?? (window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth");
    const rect = target.getBoundingClientRect();
    const top = rect.top - scroller.getBoundingClientRect().top + scroller.scrollTop + rect.height * entry.offset;
    setNavigationPage(resolvedBehavior === "smooth" ? entry.page : undefined);
    setNavigationSection(resolvedBehavior === "smooth" ? entry.index : undefined);
    scroller.scrollTo({ top: Math.max(0, top - SECTION_SCROLL_MARGIN), behavior: resolvedBehavior });
    if (resolvedBehavior === "instant") setCurrentPage(entry.page);
    if (chrome === "reader") {
      window.history.replaceState(window.history.state, "", `#pdf-section-${entry.index}`);
    }
  };
  // React-PDF retains its initial onItemClick callback. Forward through a ref so
  // links use the loaded page count and current reader callbacks. Our wrappers
  // exist even when the destination Page is unmounted by lazy rendering.
  useLayoutEffect(() => {
    internalLinkNavigation.current = jumpToPage;
    sectionNavigation.current = jumpToSection;
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
      page={navigationPage ?? page}
      pages={pages}
      zoomPercent={Math.round(zoom * 100)}
      onPage={jumpToPage}
      onZoomIn={() => setCenteredZoom((value) => stepZoom(value, 1))}
      onZoomOut={() => setCenteredZoom((value) => stepZoom(value, -1))}
      onFitWidth={() => setCenteredZoom(() => 1)}
    /> : <PdfToolbar
      paperTitle={paperTitle}
      paperHref={paperHref}
      resources={resources}
      page={navigationPage ?? page}
      pages={pages}
      zoomPercent={Math.round(zoom * 100)}
      searchOpen={searchOpen}
      searchQuery={searchQuery}
      searchMatch={activeMatch}
      searchCount={matches.length}
      searching={searching}
      onPage={jumpToPage}
      onZoom={(value) => setCenteredZoom(() => value)}
      onZoomIn={() => setCenteredZoom((value) => stepZoom(value, 1))}
      onZoomOut={() => setCenteredZoom((value) => stepZoom(value, -1))}
      onToggleSearch={() => searchOpen ? closeSearch() : setSearchOpen(true)}
      onCloseSearch={closeSearch}
      onSearchQuery={setSearchQuery}
      onSearch={navigateMatch}
    />}
    <div className="pdf-scroll-frame">
    <div ref={scrollRef} className="pdf-scroll" role="region" aria-label={chrome === "canvas" ? `${paperTitle} PDF preview` : "Paper PDF"}>
      {error ? <div className="pdf-error" role="alert">
        <p>{error}</p>
        <div><button type="button" onClick={() => setRetry((value) => value + 1)}>Retry</button> <a href={downloadUrl} target="_blank" rel="noopener noreferrer">Open PDF</a></div>
      </div> : <Document
        key={`${paperKey}-${retry}`}
        file={url}
        options={documentOptions}
        loading={<div className="pdf-loading" role="status">{chrome === "canvas" ? "Loading paper preview…" : "Loading paper…"}</div>}
        onLoadSuccess={(pdf) => {
          documentRef.current = pdf;
          textIndex.current = createPdfTextIndex(pdf);
          if (chrome === "reader") setResolveCitation(() => createPdfCitationResolver(pdf, previewCache.lookup));
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
          const section = chrome === "reader" ? pdfSectionFromHash(window.location.hash) : undefined;
          if (section === undefined) afterLayout(restorePage);
          // A malformed outline must not take the reader down with it.
          void loadPdfOutline(pdf).catch(() => []).then((entries) => {
            if (documentRef.current !== pdf) return;
            setOutline(entries);
            if (section === undefined) return;
            const entry = entries[section];
            afterLayout(() => entry ? sectionNavigation.current(entry, "instant") : restorePage());
          });
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
            aspect={pageAspect}
            searchQuery={highlightQuery}
            activeSearchPage={matches[activeMatch]}
            resolveCitation={resolveCitation}
            warmPreviews={previewCache.warm}
            highlightBoxes={shownHighlight?.boxes.filter((box) => box.page === pageNumber).map((box) => box.bbox)}
            highlightKey={highlightKey}
            highlightBrief={Boolean(citationJump)}
            onShowCitations={showCitations}
            onShowReference={showReference}
            authors={pageNumber === 1 && chrome === "reader" ? authors : undefined}
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

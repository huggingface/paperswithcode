import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Page } from "react-pdf";

import type { PdfBibliographyLink, PdfCitationResolver } from "./pdfCitationLinks";
import { PdfBibliographyEntryLink, PdfPaperLink } from "./PdfPaperLink";
import { PdfAuthorLink, type PdfPaperAuthor } from "./PdfAuthorLink";
import { pdfAuthorBoxes, type PdfAuthorBox } from "./pdfAuthorLinks";
import { usePdfPaperLinks } from "./usePdfPaperLinks";
import type { PdfHighlightBox } from "./pdfCitations";
import { highlightPdfText } from "./usePdfSearch";

// Keep each page canvas within mobile browsers' canvas area limits at high zoom.
const MAX_CANVAS_PIXELS = 16_000_000;

function pageRenderRatio(width: number, aspect: number): number {
  const maxRatio = Math.sqrt(MAX_CANVAS_PIXELS / (width * width * aspect));
  return Math.min(window.devicePixelRatio || 1, 2, maxRatio);
}

export function LazyPdfPage({
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

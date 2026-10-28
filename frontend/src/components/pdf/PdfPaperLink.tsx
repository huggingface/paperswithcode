import { useEffect } from "react";
import { createPortal } from "react-dom";
import { PaperPreviewLink } from "@/components/paper-preview/PaperPreviewLink";
import type { PdfBibliographyLink } from "./pdfCitationLinks";
import type { PdfHighlightBox } from "./pdfCitations";

export interface PdfPaperLinkTarget {
  anchor: HTMLAnchorElement;
  routeId: string;
  internal: boolean;
  /** Named destination of an in-text citation, e.g. "cite.clark2019". */
  dest?: string;
}

// Render in PDF.js's own annotation rectangle so previews stay aligned through
// zoom, rotation, and resizing, without covering selectable PDF text. A
// citation jumps to its bibliography entry and flashes it when the entry's box
// is known, and otherwise follows the PDF's own link.
export function PdfPaperLink({ anchor, routeId, internal, dest, onShowReference }: PdfPaperLinkTarget & {
  onShowReference?: (dest: string) => Promise<boolean>;
}) {
  useEffect(() => {
    const display = anchor.style.display;
    anchor.style.display = "none";
    return () => { anchor.style.display = display; };
  }, [anchor]);
  const container = anchor.parentElement;
  if (!container) return null;
  const jumpToReference = () => {
    if (!dest || !onShowReference) return anchor.click();
    void onShowReference(dest).then(shown => { if (!shown) anchor.click(); });
  };
  return createPortal(<PaperPreviewLink
    routeId={routeId}
    to={anchor.href}
    target={internal ? undefined : "_blank"}
    className="pdf-paper-preview-link"
    title={/^\d+$/.test(routeId) ? "Preview paper" : `Preview arXiv:${routeId}`}
    ariaLabel={`${internal ? 'Citation' : 'arXiv paper'} ${routeId}`}
    cardOpensPaper
    onClick={internal ? (event) => {
      // Keep citation clicks as in-document navigation, including on touch.
      event.preventDefault();
      jumpToReference();
    } : undefined}
    previewFooter={() => <div className="pdf-paper-preview-actions">
      <a href={`/paper/${encodeURIComponent(routeId)}`} target="_blank" rel="noopener noreferrer">Open paper ↗</a>
      {internal && <button type="button" onClick={jumpToReference}>Jump to reference</button>}
    </div>}
  >{null}</PaperPreviewLink>, container);
}

// A bibliography entry has no PDF link of its own, so its preview target is
// positioned over the entry's text on the page's 0–1000 grid. Its card jumps
// back to where the text cites it; the viewer steps through the rest.
export function PdfBibliographyEntryLink({ routeId, box: [x0, y0, x1, y1], citations = [], onShowCitations }: PdfBibliographyLink & {
  citations?: PdfHighlightBox[][];
  onShowCitations?: (citations: PdfHighlightBox[][]) => void;
}) {
  return <div
    className="pdf-bibliography-link"
    style={{ left: `${x0 / 10}%`, top: `${y0 / 10}%`, width: `${(x1 - x0) / 10}%`, height: `${(y1 - y0) / 10}%` }}
  >
    <PaperPreviewLink
      routeId={routeId}
      to={`/paper/${encodeURIComponent(routeId)}`}
      target="_blank"
      className="pdf-paper-preview-link"
      title={/^\d+$/.test(routeId) ? "Preview paper" : `Preview arXiv:${routeId}`}
      ariaLabel={`Reference ${routeId}`}
      cardOpensPaper
      previewFooter={() => <div className="pdf-paper-preview-actions">
        <a href={`/paper/${encodeURIComponent(routeId)}`} target="_blank" rel="noopener noreferrer">Open paper ↗</a>
        {citations.length > 0 && onShowCitations && <button type="button" onClick={() => onShowCitations(citations)}>
          {citations.length > 1 ? `Jump to citations (${citations.length})` : "Jump to citation"}
        </button>}
      </div>}
    >{null}</PaperPreviewLink>
  </div>;
}

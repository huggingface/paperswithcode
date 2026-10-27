import { useEffect } from "react";
import { createPortal } from "react-dom";
import { PaperPreviewLink } from "@/components/paper-preview/PaperPreviewLink";
import type { PdfBibliographyLink } from "./pdfCitationLinks";

export interface PdfPaperLinkTarget {
  anchor: HTMLAnchorElement;
  routeId: string;
  internal: boolean;
}

// Render in PDF.js's own annotation rectangle so previews stay aligned through
// zoom, rotation, and resizing, without covering selectable PDF text.
export function PdfPaperLink({ anchor, routeId, internal }: PdfPaperLinkTarget) {
  useEffect(() => {
    const display = anchor.style.display;
    anchor.style.display = "none";
    return () => { anchor.style.display = display; };
  }, [anchor]);
  const container = anchor.parentElement;
  if (!container) return null;
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
      anchor.click();
    } : undefined}
    previewFooter={() => <div className="pdf-paper-preview-actions">
      <a href={`/paper/${encodeURIComponent(routeId)}`} target="_blank" rel="noopener noreferrer">Open paper ↗</a>
      {internal && <button type="button" onClick={() => anchor.click()}>Jump to reference</button>}
    </div>}
  >{null}</PaperPreviewLink>, container);
}

// A bibliography entry has no PDF link of its own, so its preview target is
// positioned over the entry's text on the page's 0–1000 grid.
export function PdfBibliographyEntryLink({ routeId, box: [x0, y0, x1, y1] }: PdfBibliographyLink) {
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
    >{null}</PaperPreviewLink>
  </div>;
}

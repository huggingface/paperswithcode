import { useState } from "react";
import type { FormEvent } from "react";

import type { PaperSelectionDraft } from "@/lib/chat";
import { PdfToolbar } from "./PdfToolbar";
import type { PdfToolbarResources } from "./PdfToolbar";
import type { PdfPaperAuthor } from "./PdfAuthorLink";
import type { PdfHighlight } from "./pdfCitations";
import { stepZoom } from "./pdfZoom";
import { PdfDocumentView, type PdfViewerControls } from "./PdfDocumentView";

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

// Canvas previews are private artifact endpoints. Public reader PDFs must keep
// their normal cross-origin fetch behavior, and fetch only the byte ranges
// that visible pages, search, and citations need when the server allows it.
const READER_DOCUMENT_OPTIONS = { disableStream: true, disableAutoFetch: true };
const CANVAS_DOCUMENT_OPTIONS = { withCredentials: true };

function CanvasPdfToolbar({ downloadUrl, page, pages, zoom, onPage, onZoom }: PdfViewerControls & { downloadUrl: string }) {
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
      <button type="button" onClick={() => onZoom((value) => stepZoom(value, -1))} aria-label="Zoom out">−</button>
      <output aria-live="polite">{Math.round(zoom * 100)}%</output>
      <button type="button" onClick={() => onZoom((value) => stepZoom(value, 1))} aria-label="Zoom in">+</button>
      <button type="button" onClick={() => onZoom(() => 1)}>Fit to width</button>
      <a href={downloadUrl} download>Download PDF</a>
    </div>
  </div>;
}

/**
 * The paper reader's PDF surface, or (`chrome="canvas"`) a bare preview of a
 * private chat artifact without the reader's search, citation cards, author
 * links, and section deep links.
 */
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
  chrome = "reader",
  authors,
  ...rest
}: PdfViewerProps) {
  const [retry, setRetry] = useState(0);
  const reader = chrome === "reader";
  const toolbar = (controls: PdfViewerControls) => reader ? <PdfToolbar
    paperTitle={paperTitle}
    paperHref={paperHref}
    resources={resources}
    page={controls.page}
    pages={controls.pages}
    zoomPercent={Math.round(controls.zoom * 100)}
    searchOpen={controls.search.open}
    searchQuery={controls.search.query}
    searchMatch={controls.search.activeMatch}
    searchCount={controls.search.matches.length}
    searching={controls.search.searching}
    onPage={controls.onPage}
    onZoom={(value) => controls.onZoom(() => value)}
    onZoomIn={() => controls.onZoom((value) => stepZoom(value, 1))}
    onZoomOut={() => controls.onZoom((value) => stepZoom(value, -1))}
    onToggleSearch={() => controls.search.open ? controls.search.close() : controls.search.setOpen(true)}
    onCloseSearch={controls.search.close}
    onSearchQuery={controls.search.setQuery}
    onSearch={controls.search.navigate}
  /> : <CanvasPdfToolbar downloadUrl={downloadUrl} {...controls} />;

  return <PdfDocumentView
    key={`${paperKey}-${retry}-${initialPage}`}
    {...rest}
    url={url}
    downloadUrl={downloadUrl}
    paperKey={paperKey}
    initialPage={initialPage}
    resizeActive={resizeActive}
    selectionEnabled={selectionEnabled}
    paperVersion={paperVersion}
    documentOptions={reader ? READER_DOCUMENT_OPTIONS : CANVAS_DOCUMENT_OPTIONS}
    label={reader ? "Paper PDF" : `${paperTitle} PDF preview`}
    loadingLabel={reader ? "Loading paper…" : "Loading paper preview…"}
    toolbar={toolbar}
    onRetry={() => setRetry((value) => value + 1)}
    citationLinks={reader}
    sectionHash={reader}
    authors={reader ? authors : undefined}
  />;
}

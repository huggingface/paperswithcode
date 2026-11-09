import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import MarkdownText from "@/components/MarkdownText";
import { ReaderToolbar, type PdfToolbarResources } from "@/components/pdf/PdfToolbar";
import { usePdfSelection } from "@/hooks/usePdfSelection";
import { paperQueries } from "@/lib/api/queries";
import { ApiError } from "@/lib/apiTransport";
import type { PaperSelectionDraft } from "@/lib/chat";
import { framesOriginalPage, sameWebPage, webPaperBody } from "@/lib/paperReader";

function loadErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 422) {
    return "This page could not be turned into a readable paper.";
  }
  if (error instanceof ApiError && error.status === 503) {
    return "Paper content is still being prepared. Please try again later.";
  }
  return "The paper could not be loaded.";
}

interface WebPaperViewerProps {
  paperId: string;
  paperKey: string;
  paperTitle: string;
  paperHref: string;
  sourceUrl: string;
  resources?: PdfToolbarResources;
  paperVersion?: string;
  selectionEnabled?: boolean;
  onReady?: () => void;
  onPaperSelection?: (selection: PaperSelectionDraft) => void;
  onPaperSelectionError?: (message: string) => void;
}

/**
 * Reads an HTML-only external paper in the reader: its original page where the
 * host allows framing, or its Markdown, which text selection for chat needs.
 */
export function WebPaperViewer({
  paperId,
  paperKey,
  paperTitle,
  paperHref,
  sourceUrl,
  resources,
  paperVersion = "",
  selectionEnabled = false,
  onReady,
  onPaperSelection,
  onPaperSelectionError,
}: WebPaperViewerProps) {
  const documentRef = useRef<HTMLElement>(null);
  const knownFrameable = framesOriginalPage(sourceUrl);
  const pageQuery = useQuery({
    ...paperQueries.webPage(paperId),
    enabled: !knownFrameable,
    // Without an answer the page is read as Markdown.
    retry: false,
  });
  const deciding = !knownFrameable && pageQuery.isPending;
  const frameable = knownFrameable || pageQuery.data?.frameable === true;
  const [view, setView] = useState<"original" | "text">("original");
  const showOriginal = frameable && view === "original";
  const query = useQuery({
    ...paperQueries.webMarkdown(paperId),
    // The first read may still be preparing the page; 4xx answers are final.
    retry: (count, error) => count < 2 && !(error instanceof ApiError && error.status < 500),
    retryDelay: 3000,
  });
  const ready = query.isSuccess;

  useEffect(() => {
    if (ready) onReady?.();
  }, [onReady, ready]);

  usePdfSelection({
    enabled: selectionEnabled && Boolean(paperVersion) && ready && !showOriginal,
    pagesRoot: documentRef,
    routeId: paperKey,
    paperVersion,
    numPages: 1,
    onSelect: onPaperSelection,
    onError: onPaperSelectionError,
  });

  const body = query.data ? webPaperBody(query.data) : "";
  // The project-page chip already opens the original when it is the same page.
  const projectPageIsOriginal = Boolean(resources?.projectPage && sameWebPage(resources.projectPage.href, sourceUrl));
  return <div className="pdf-viewer">
    <ReaderToolbar paperTitle={paperTitle} paperHref={paperHref} resources={resources} label="Paper controls">
      <div className="pdf-toolbar-controls">
        {frameable && <div className="reader-web-view-toggle" role="group" aria-label="Paper view">
          <button type="button" aria-pressed={showOriginal} onClick={() => setView("original")}>Original</button>
          <button
            type="button"
            aria-pressed={!showOriginal}
            title="Readable text; select a passage to ask the chat about it"
            onClick={() => setView("text")}
          >Text</button>
        </div>}
        {!projectPageIsOriginal && <a href={sourceUrl} target="_blank" rel="noopener noreferrer">Open original</a>}
      </div>
    </ReaderToolbar>
    <div className="pdf-scroll-frame">
      {deciding ? <div className="pdf-loading" role="status">Loading the paper…</div>
        : showOriginal ? <iframe
          className="reader-web-frame"
          src={sourceUrl}
          title={`Original page: ${paperTitle}`}
          sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
          referrerPolicy="strict-origin-when-cross-origin"
        />
        : <div className="pdf-scroll" role="region" aria-label="Paper web page">
          {query.isPending ? <div className="pdf-loading" role="status">Preparing a readable version of this page…</div>
            : query.isError ? <div className="pdf-error" role="alert">
              <p>{loadErrorMessage(query.error)}</p>
              <div>
                <button type="button" onClick={() => void query.refetch()}>Retry</button>
                {" "}<a href={sourceUrl} target="_blank" rel="noopener noreferrer">Open original</a>
              </div>
            </div>
            : <article ref={documentRef} className="reader-web-document" data-page="1">
              {!body.startsWith("# ") && <h1>{paperTitle}</h1>}
              <MarkdownText text={body} />
            </article>}
        </div>}
    </div>
  </div>;
}

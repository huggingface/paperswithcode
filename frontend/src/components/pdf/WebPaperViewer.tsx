import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";

import MarkdownText from "@/components/MarkdownText";
import { ReaderToolbar, type PdfToolbarResources } from "@/components/pdf/PdfToolbar";
import { usePdfSelection } from "@/hooks/usePdfSelection";
import { getPaperWebMarkdown } from "@/lib/api/papers";
import { ApiError } from "@/lib/apiTransport";
import type { PaperSelectionDraft } from "@/lib/chat";
import { webPaperBody } from "@/lib/paperReader";

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

/** Reads an HTML-only external paper as one Markdown page in the reader. */
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
  const query = useQuery({
    queryKey: ["paperWebMarkdown", paperId],
    queryFn: () => getPaperWebMarkdown(paperId),
    staleTime: 5 * 60_000,
    // The first read may still be preparing the page; 4xx answers are final.
    retry: (count, error) => count < 2 && !(error instanceof ApiError && error.status < 500),
    retryDelay: 3000,
  });
  const ready = query.isSuccess;

  useEffect(() => {
    if (ready) onReady?.();
  }, [onReady, ready]);

  usePdfSelection({
    enabled: selectionEnabled && Boolean(paperVersion) && ready,
    pagesRoot: documentRef,
    routeId: paperKey,
    paperVersion,
    numPages: 1,
    onSelect: onPaperSelection,
    onError: onPaperSelectionError,
  });

  const body = query.data ? webPaperBody(query.data) : "";
  return <div className="pdf-viewer">
    <ReaderToolbar paperTitle={paperTitle} paperHref={paperHref} resources={resources} label="Paper controls">
      <div className="pdf-toolbar-controls">
        <a href={sourceUrl} target="_blank" rel="noopener noreferrer">Open original</a>
      </div>
    </ReaderToolbar>
    <div className="pdf-scroll-frame">
      <div className="pdf-scroll" role="region" aria-label="Paper web page">
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
      </div>
    </div>
  </div>;
}

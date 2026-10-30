import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { PdfViewer } from "@/components/pdf/PdfViewer";
import { WebPaperViewer } from "@/components/pdf/WebPaperViewer";
import { ArtifactWorkspace } from "@/components/chat/ArtifactWorkspace";
import { ArtifactPanelProvider, useArtifactPanel } from "@/components/chat/useArtifactPanel";
import type { PdfToolbarResources } from "@/components/pdf/PdfToolbar";
import { usePaper } from "@/hooks/usePapers";
import type { Paper } from "@/lib/api/papers.types";
import { assetUrl, isPaperReaderChatEnabled } from "@/lib/apiUrl";
import { chatApi } from "@/lib/api/chat";
import type { PaperSelectionDraft } from "@/lib/chat";
import { safeExternalHref } from "@/lib/safeExternalHref";
import { externalPaperWebPage, readerCollapsedKey, readerPageKey, readerSessionKey } from "@/lib/paperReader";
import { normalizePaperRouteId } from "@/lib/utils";
import { ChatExperience } from "@/views/ChatView";
import { PdfCitationContext, type PdfCitationTarget } from "@/components/chat/PdfCitationContext";
import { citationBoxes, type PdfHighlight } from "@/components/pdf/pdfCitations";
import { getPaperLayout } from "@/lib/api/papers";

const DEFAULT_RATIO = 66;
const CHAT_TRANSITION_MS = 240;
const RATIO_KEY = "pwc:reader:split-ratio";

function storedPage(routeId: string): number {
  const value = Number(sessionStorage.getItem(readerPageKey(routeId)));
  return Number.isInteger(value) && value > 0 ? value : 1;
}

function storedRatio(): number {
  const value = Number(localStorage.getItem(RATIO_KEY));
  return Number.isFinite(value) && value >= 45 && value <= 75 ? value : DEFAULT_RATIO;
}

function directArxivPdfHref(value: unknown): string | null {
  const href = safeExternalHref(value);
  if (!href) return null;
  const parsed = new URL(href);
  if (
    (parsed.hostname === "arxiv.org" || parsed.hostname === "www.arxiv.org")
    && parsed.pathname.startsWith("/pdf/")
    && parsed.pathname.endsWith(".pdf")
  ) {
    parsed.pathname = parsed.pathname.slice(0, -4);
  }
  return parsed.href;
}

const ARXIV_PDF_PATH = /^\/pdf\/(\d{4}\.\d{4,5}(?:v\d{1,3})?|[a-z]+(?:-[a-z]+)*(?:\.[A-Z]{2})?\/\d{7}(?:v\d{1,3})?)$/;

// arXiv hides Accept-Ranges from cross-origin fetches, which makes pdf.js
// download the whole file before page 1. nginx serves arXiv PDFs same-origin
// with range requests intact.
function rangeReadablePdfHref(href: string): string {
  const parsed = new URL(href);
  const match = parsed.pathname.match(ARXIV_PDF_PATH);
  if ((parsed.hostname === "arxiv.org" || parsed.hostname === "www.arxiv.org") && match && !parsed.search) {
    return assetUrl(`/paper-assets/arxiv-pdf/${match[1]}`) ?? href;
  }
  return href;
}

function resourceHostname(href: string): string {
  return new URL(href).hostname.replace(/^www\./, "");
}

export function readerToolbarResources(paper: Paper | undefined): PdfToolbarResources {
  if (!paper) return {};
  const resources: PdfToolbarResources = {};
  for (const repository of paper.repositories ?? []) {
    if (!repository.is_official) continue;
    const href = safeExternalHref(repository.url);
    if (!href) continue;
    const parsed = new URL(href);
    const parts = parsed.pathname.split("/").filter(Boolean);
    if ((parsed.hostname === "github.com" || parsed.hostname === "www.github.com")
      && parts.length >= 2) {
      resources.repository = {
        href,
        stars: repository.num_stars || 0,
      };
      break;
    }
  }
  const projectPages = [...(paper.project_pages ?? [])]
    .sort((left, right) => Number(right.is_official) - Number(left.is_official));
  for (const projectPage of projectPages) {
    const href = safeExternalHref(projectPage.url);
    if (!href) continue;
    resources.projectPage = { href, label: resourceHostname(href) };
    break;
  }
  const artifactCount = paper.hf_artifact_summary
    ? paper.hf_artifact_summary.model_count
      + paper.hf_artifact_summary.dataset_count
      + paper.hf_artifact_summary.space_count
    : new Set([...(paper.hf_models ?? []), ...(paper.hf_datasets ?? []), ...(paper.hf_spaces ?? [])]).size;
  if (artifactCount > 0 && paper.arxiv_id) {
    resources.huggingFace = {
      href: `https://huggingface.co/papers/${paper.arxiv_id.replace(/v\d+$/i, "")}`,
      count: artifactCount,
    };
  }
  return resources;
}

// Keyed by routeId, so another paper starts from its own stored reader state.
function PaperReaderExperience({ routeId }: { routeId: string }) {
  const navigate = useNavigate();
  const query = usePaper(routeId, Boolean(routeId));
  const availabilityQuery = useQuery({
    queryKey: ["chatAvailability"],
    queryFn: () => chatApi.getAvailability(),
    refetchInterval: 30000,
    retry: false,
  });
  const paper = query.data;
  const webPage = paper ? externalPaperWebPage(paper) : null;
  const originalPdfUrl = webPage ? null : paper?.source === "external"
    ? assetUrl(`/paper-assets/external/${paper.id}/paper.pdf`)
    : directArxivPdfHref(paper?.url_pdf);
  const pdfUrl = originalPdfUrl && paper?.source !== "external"
    ? rangeReadablePdfHref(originalPdfUrl)
    : originalPdfUrl;
  const toolbarResources = readerToolbarResources(paper);
  const authors = useMemo(() => paper?.author_links?.flatMap((author) => author.id
    ? [{ id: author.id, name: author.name, avatarUrl: author.hf_avatar_url }]
    : []), [paper?.author_links]);
  const canonicalRoute = paper?.arxiv_id?.replace(/v\d+$/i, "") || routeId;
  const closeReader = useCallback(() => navigate(`/paper/${canonicalRoute}`), [canonicalRoute, navigate]);
  const [activeSessionId, setActiveSessionId] = useState<string | undefined>(() => {
    const stored = sessionStorage.getItem(readerSessionKey(routeId));
    return stored || undefined;
  });
  const [ratio, setRatio] = useState(storedRatio);
  const [collapsed, setCollapsed] = useState(
    () => sessionStorage.getItem(readerCollapsedKey(routeId)) === "1",
  );
  const [mobileTab, setMobileTab] = useState<"paper" | "assistant">("paper");
  const [paperSelection, setPaperSelection] = useState<PaperSelectionDraft | undefined>();
  const [pdfHighlight, setPdfHighlight] = useState<PdfHighlight>();
  // Chat waits for a web paper's Markdown so its first turn can read the page.
  const [webPageReady, setWebPageReady] = useState(false);
  const markWebPageReady = useCallback(() => setWebPageReady(true), []);
  const [selectionStatus, setSelectionStatus] = useState("");
  const [initialPage] = useState(() => storedPage(routeId));
  const [workspaceWidth, setWorkspaceWidth] = useState(0);
  const [resizeActive, setResizeActive] = useState(false);
  const [chatTransitionActive, setChatTransitionActive] = useState(false);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const paperPaneRef = useRef<HTMLElement>(null);
  const assistantPaneRef = useRef<HTMLElement>(null);
  const resizeHandleRef = useRef<HTMLDivElement>(null);
  const chatToggleRef = useRef<HTMLButtonElement>(null);
  const focusAfterToggle = useRef(false);
  const dragging = useRef(false);
  const chatTransitionTimer = useRef(0);
  const resizeFrame = useRef(0);
  const pendingClientX = useRef(0);
  const pendingRatio = useRef(ratio);
  const currentPageRef = useRef(initialPage);
  const paperVersionRef = useRef(paper?.version);
  const artifactPanel = useArtifactPanel();
  const resetArtifactPanel = artifactPanel.reset;
  const artifactSessionRef = useRef(activeSessionId);
  const desktopSplit = workspaceWidth >= 840;

  useEffect(() => {
    if (artifactSessionRef.current === activeSessionId) return;
    artifactSessionRef.current = activeSessionId;
    resetArtifactPanel();
  }, [activeSessionId, resetArtifactPanel]);

  useEffect(() => {
    if (paper?.version && paperVersionRef.current && paper.version !== paperVersionRef.current) {
      setPaperSelection(undefined);
      setSelectionStatus("");
    }
    paperVersionRef.current = paper?.version;
  }, [paper?.version]);

  useEffect(() => () => {
    window.clearTimeout(chatTransitionTimer.current);
    cancelAnimationFrame(resizeFrame.current);
  }, []);

  useLayoutEffect(() => {
    const element = workspaceRef.current;
    if (!element) return;
    const update = () => setWorkspaceWidth(element.clientWidth);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [paper]);

  useEffect(() => {
    if (!paper) return;
    document.title = `${paper.title} — Papers With Code reader`;
    let robots = document.querySelector<HTMLMetaElement>('meta[name="robots"]');
    const createdRobots = !robots;
    if (!robots) {
      robots = document.createElement("meta");
      robots.name = "robots";
      document.head.appendChild(robots);
    }
    const priorRobots = robots.content;
    robots.content = "noindex, nofollow";
    let canonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    const createdCanonical = !canonical;
    if (!canonical) {
      canonical = document.createElement("link");
      canonical.rel = "canonical";
      document.head.appendChild(canonical);
    }
    const priorCanonical = canonical.href;
    canonical.href = `${window.location.origin}/paper/${canonicalRoute}`;
    return () => {
      document.title = "Papers With Code";
      if (createdRobots) robots?.remove(); else if (robots) robots.content = priorRobots;
      if (createdCanonical) canonical?.remove(); else if (canonical) canonical.href = priorCanonical;
    };
  }, [canonicalRoute, paper]);

  const clampRatio = useCallback((next: number) => {
    if (!workspaceWidth) return Math.max(45, Math.min(75, next));
    const minimumPdf = 480 / workspaceWidth * 100;
    const maximumPdf = 100 - 360 / workspaceWidth * 100;
    return Math.max(minimumPdf, Math.min(maximumPdf, next));
  }, [workspaceWidth]);

  useEffect(() => setRatio((value) => {
    const bounded = clampRatio(value);
    pendingRatio.current = bounded;
    return bounded;
  }), [clampRatio]);

  const setSavedRatio = (next: number) => {
    const bounded = clampRatio(next);
    pendingRatio.current = bounded;
    setRatio(bounded);
    localStorage.setItem(RATIO_KEY, String(bounded));
  };
  const applyLiveRatio = (next: number) => {
    const bounded = clampRatio(next);
    pendingRatio.current = bounded;
    if (paperPaneRef.current) paperPaneRef.current.style.width = `${bounded}%`;
    if (assistantPaneRef.current) assistantPaneRef.current.style.width = `${100 - bounded}%`;
    resizeHandleRef.current?.setAttribute("aria-valuenow", String(Math.round(bounded)));
  };
  const resizeFromPointer = (clientX: number) => {
    pendingClientX.current = clientX;
    if (resizeFrame.current) return;
    resizeFrame.current = requestAnimationFrame(() => {
      resizeFrame.current = 0;
      const rect = workspaceRef.current?.getBoundingClientRect();
      if (!rect?.width) return;
      applyLiveRatio((pendingClientX.current - rect.left) / rect.width * 100);
    });
  };
  const pointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    setResizeActive(true);
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeFromPointer(event.clientX);
  };
  const finishResize = () => {
    if (!dragging.current) return;
    if (resizeFrame.current) {
      cancelAnimationFrame(resizeFrame.current);
      resizeFrame.current = 0;
      const rect = workspaceRef.current?.getBoundingClientRect();
      if (rect?.width) applyLiveRatio((pendingClientX.current - rect.left) / rect.width * 100);
    }
    dragging.current = false;
    setRatio(pendingRatio.current);
    localStorage.setItem(RATIO_KEY, String(pendingRatio.current));
    setResizeActive(false);
  };
  const setAssistantCollapsed = (next: boolean) => {
    window.clearTimeout(chatTransitionTimer.current);
    setChatTransitionActive(true);
    setCollapsed(next);
    sessionStorage.setItem(readerCollapsedKey(routeId), next ? "1" : "0");
    chatTransitionTimer.current = window.setTimeout(
      () => setChatTransitionActive(false),
      CHAT_TRANSITION_MS + 40,
    );
  };
  // Keyboard users keep their place: closing focuses the floating toggle, opening focuses the pane.
  const toggleAssistant = (next: boolean) => {
    focusAfterToggle.current = true;
    setAssistantCollapsed(next);
  };
  useEffect(() => {
    if (!focusAfterToggle.current) return;
    focusAfterToggle.current = false;
    (collapsed ? chatToggleRef.current : assistantPaneRef.current)?.focus();
  }, [collapsed]);
  const selectSession = (id: string) => {
    setActiveSessionId(id);
    sessionStorage.setItem(readerSessionKey(routeId), id);
  };
  const newChat = () => {
    setActiveSessionId(undefined);
    sessionStorage.removeItem(readerSessionKey(routeId));
    setPaperSelection(undefined);
    setSelectionStatus("");
  };

  const selectionEnabled = availabilityQuery.data?.paper_reader_selection_enabled === true;
  const attachSelection = (selection: PaperSelectionDraft) => {
    setPaperSelection(selection);
    setSelectionStatus(`Selection from page ${selection.page} added to chat`);
    if (desktopSplit && collapsed) setAssistantCollapsed(false);
  };
  const handlePaperSelectionChange = useCallback((selection?: PaperSelectionDraft) => {
    setPaperSelection(selection);
    if (!selection) setSelectionStatus("");
  }, []);

  const citationsEnabled = availabilityQuery.data?.paper_reader_citations_enabled === true && Boolean(pdfUrl);
  const layoutQuery = useQuery({
    queryKey: ["paper-layout", canonicalRoute],
    queryFn: () => getPaperLayout(canonicalRoute),
    enabled: citationsEnabled && Boolean(canonicalRoute),
    staleTime: 5 * 60_000,
  });
  const layout = layoutQuery.data;
  const citationTarget = useMemo<PdfCitationTarget | null>(() => citationsEnabled ? {
    layout,
    open: (anchor) => {
      const boxes = layout ? citationBoxes(layout, anchor) : [];
      if (!boxes.length) return;
      setPdfHighlight((previous) => ({ boxes, nonce: (previous?.nonce ?? 0) + 1 }));
      setMobileTab("paper");
    },
  } : null, [citationsEnabled, layout]);

  const assistantEnabled = isPaperReaderChatEnabled()
    && availabilityQuery.data?.paper_reader_chat_enabled !== false;
  const chatReady = Boolean(paper && assistantEnabled && !(webPage && !webPageReady));
  const assistant = paper && assistantEnabled && !chatReady
    ? <div className="reader-chat-unavailable" role="status">Chat opens once the paper is ready.</div>
    : paper && chatReady ? <ChatExperience
    mode="paper"
    routeSessionId={activeSessionId}
    primaryPaper={{ id: paper.id, routeId: canonicalRoute, title: paper.title }}
    currentPage={() => currentPageRef.current}
    paperSelection={paperSelection}
    onPaperSelectionChange={handlePaperSelectionChange}
    onSessionId={selectSession}
    onReaderSubmit={() => setMobileTab("assistant")}
    onReaderNewChat={newChat}
    onReaderClose={desktopSplit ? () => toggleAssistant(true) : undefined}
  /> : <div className="reader-chat-unavailable">Chat is not enabled for this preview.</div>;

  if (query.isLoading) return <div className="reader-status" role="status">Loading paper…</div>;
  if (query.error || !paper) return <div className="reader-status" role="alert"><p>Paper not found.</p><Link to="/papers">Browse papers</Link></div>;
  if (availabilityQuery.data?.native_pdf_reader_enabled === false) return <div className="reader-status" role="alert"><p>The native reader is currently unavailable.</p><Link to={`/paper/${canonicalRoute}`}>Back to paper</Link></div>;
  if (!pdfUrl && !webPage) return <div className="reader-status" role="alert"><p>Native reading is unavailable for this resource.</p><Link to={`/paper/${canonicalRoute}`}>Back to paper</Link></div>;

  return <div className="paper-reader-shell">
    {!desktopSplit && <div className="reader-tabs" role="tablist" aria-label="Reader panels">
      <button type="button" role="tab" aria-selected={mobileTab === "paper"} onClick={() => setMobileTab("paper")}>Paper</button>
      <button
        type="button"
        role="tab"
        aria-selected={mobileTab === "assistant"}
        aria-label={paperSelection && mobileTab !== "assistant" ? "Chat, selection attached" : "Chat"}
        onClick={() => setMobileTab("assistant")}
      >
        Chat
        {paperSelection && mobileTab !== "assistant" && <span className="reader-tab-pending" aria-hidden="true" />}
      </button>
    </div>}
    <ArtifactWorkspace variant="reader">
    <div ref={workspaceRef} className={`reader-workspace${desktopSplit ? " is-desktop" : " is-tabs"}${collapsed ? " is-assistant-collapsed" : ""}${resizeActive ? " is-resizing" : ""}`} data-testid="paper-chat-workspace">
      <section
        ref={paperPaneRef}
        className={`reader-paper-pane${!desktopSplit && mobileTab !== "paper" ? " is-hidden" : ""}`}
        style={desktopSplit ? { width: collapsed ? "100%" : `${ratio}%` } : undefined}
        role="tabpanel"
        aria-label="Paper"
        aria-hidden={!desktopSplit && mobileTab !== "paper"}
      >
        {webPage ? <WebPaperViewer
          paperId={paper.id}
          paperKey={canonicalRoute}
          paperTitle={paper.title}
          paperHref={`/paper/${canonicalRoute}`}
          sourceUrl={webPage}
          resources={toolbarResources}
          paperVersion={paper.version}
          selectionEnabled={selectionEnabled}
          onReady={markWebPageReady}
          onPaperSelection={attachSelection}
          onPaperSelectionError={setSelectionStatus}
        /> : pdfUrl && (
          <PdfViewer
            url={pdfUrl}
            downloadUrl={originalPdfUrl ?? pdfUrl}
            paperKey={canonicalRoute}
            paperTitle={paper.title}
            paperHref={`/paper/${canonicalRoute}`}
            onClose={closeReader}
            resources={toolbarResources}
            initialPage={initialPage}
            resizeActive={resizeActive || chatTransitionActive}
            selectionEnabled={selectionEnabled}
            paperVersion={paper.version}
            authors={authors}
            loadErrorMessage={paper.source === "external"
              ? "Paper content is still being prepared. Please try again later."
              : undefined}
            onPaperSelection={attachSelection}
            onPaperSelectionError={setSelectionStatus}
            highlight={pdfHighlight}
            onPageChange={(page) => {
              currentPageRef.current = page;
              sessionStorage.setItem(readerPageKey(routeId), String(page));
            }}
          />
        )}
      </section>
      {desktopSplit && !collapsed && <div
        ref={resizeHandleRef}
        className="reader-resize-handle"
        role="separator"
        aria-label="Resize paper and Chat panels"
        aria-orientation="vertical"
        aria-valuemin={45}
        aria-valuemax={75}
        aria-valuenow={Math.round(ratio)}
        tabIndex={0}
        onPointerDown={pointerDown}
        onPointerMove={(event) => { if (dragging.current) resizeFromPointer(event.clientX); }}
        onPointerUp={finishResize}
        onPointerCancel={finishResize}
        onLostPointerCapture={finishResize}
        onDoubleClick={() => setSavedRatio(DEFAULT_RATIO)}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            setSavedRatio(ratio + (event.key === "ArrowRight" ? 2 : -2));
          }
          if (event.key === "Home") setSavedRatio(45);
          if (event.key === "End") setSavedRatio(75);
        }}
      />}
      <aside
        ref={assistantPaneRef}
        id="reader-chat-panel"
        className={`reader-assistant-pane${!desktopSplit && mobileTab !== "assistant" ? " is-hidden" : ""}${desktopSplit && collapsed ? " is-collapsed" : ""}`}
        style={desktopSplit ? { width: collapsed ? 0 : `${100 - ratio}%` } : undefined}
        role="tabpanel"
        aria-label="Chat"
        aria-hidden={(!desktopSplit && mobileTab !== "assistant") || collapsed}
        tabIndex={-1}
      ><PdfCitationContext.Provider value={citationTarget}>{assistant}</PdfCitationContext.Provider></aside>
      <div className="sr-only" aria-live="polite">{selectionStatus}</div>
      {/* A ready chat closes from its own topbar; other panes keep the floating toggle. */}
      {desktopSplit && (collapsed || !chatReady) && <button
        ref={chatToggleRef}
        type="button"
        className="reader-collapse-assistant"
        aria-controls="reader-chat-panel"
        aria-expanded={!collapsed}
        onClick={() => toggleAssistant(!collapsed)}
      >{collapsed ? "Open chat" : "Hide chat"}</button>}
    </div>
    </ArtifactWorkspace>
  </div>;
}

export default function PaperReaderView() {
  const { paperId = "" } = useParams<{ paperId: string }>();
  const routeId = normalizePaperRouteId(paperId).replace(/v\d+$/i, "");
  return <ArtifactPanelProvider workspaceKey={`reader:${paperId}`}>
    <PaperReaderExperience key={routeId} routeId={routeId} />
  </ArtifactPanelProvider>;
}

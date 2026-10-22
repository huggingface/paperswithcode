import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getAvailability: vi.fn(),
  getPaperWebMarkdown: vi.fn(),
  showArtifact: false,
  paper: {} as Record<string, unknown>,
}));

vi.mock("@/hooks/usePapers", () => ({
  usePaper: () => ({
    data: mocks.paper,
    isLoading: false,
    error: null,
  }),
}));

const arxivPaper = {
      id: "42",
      arxiv_id: "1706.03762",
      title: "Attention Is All You Need",
      source: "arxiv",
      version: "v7",
      url_pdf: "https://arxiv.org/pdf/1706.03762v7.pdf",
      repositories: [
        { id: "1", paper_id: "42", url: "https://github.com/attention-is-all-you-need/paper", owner: "Attention", name: "paper", num_stars: 1200, is_official: true, source: "curated" },
        { id: "2", paper_id: "42", url: "https://github.com/community/paper", num_stars: 2, is_official: false, source: "curated" },
      ],
      project_pages: [
        { id: "3", paper_id: "42", url: "https://attention.example/project", is_official: true, source: "curated" },
      ],
      hf_artifact_summary: { model_count: 2, dataset_count: 1, space_count: 0, best_kind: "model", best_count: 2, best_url: "https://huggingface.co/models?other=arxiv:1706.03762" },
};
vi.mock("@/lib/api/papers", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api/papers")>(),
  getPaperWebMarkdown: mocks.getPaperWebMarkdown,
}));
vi.mock("@/lib/api/chat", () => ({
  chatApi: { getAvailability: mocks.getAvailability },
}));
vi.mock("@/components/pdf/PdfViewer", () => ({
  PdfViewer: ({ url, downloadUrl, paperTitle, paperHref, resources, resizeActive, selectionEnabled, paperVersion, onPaperSelection }: {
    url: string;
    downloadUrl?: string;
    paperTitle: string;
    paperHref: string;
    resizeActive?: boolean;
    selectionEnabled?: boolean;
    paperVersion?: string;
    onPaperSelection?: (selection: { routeId: string; paperVersion: string; page: number; text: string }) => void;
    resources?: {
      repository?: { href: string; stars: number };
      projectPage?: { href: string; label: string };
      huggingFace?: { href: string; count: number };
    };
  }) => <div>
    <a href={paperHref} aria-label={`${paperTitle} — open paper page`}>{paperTitle}</a>
    {resources?.repository && <a href={resources.repository.href}>Official repository · {resources.repository.stars} stars</a>}
    {resources?.projectPage && <a href={resources.projectPage.href}>Project page</a>}
    {resources?.huggingFace && <a href={resources.huggingFace.href}>{resources.huggingFace.count} HF artifacts</a>}
    <div role="region" aria-label="Paper PDF" data-url={url} data-download-url={downloadUrl} data-resize-active={String(Boolean(resizeActive))} data-selection-enabled={String(Boolean(selectionEnabled))} data-paper-version={paperVersion || ""}>PDF viewer</div>
    <button type="button" onClick={() => onPaperSelection?.({
      routeId: "1706.03762",
      paperVersion: paperVersion || "v7",
      page: 4,
      text: "Attention Is All You Need",
    })}>Attach selection</button>
  </div>,
}));
vi.mock("@/views/ChatView", async () => {
  const { PosterArtifact } = await import("@/components/chat/PosterArtifact");
  return {
    ChatExperience: ({ paperSelection, onReaderClose }: { paperSelection?: { page: number }; onReaderClose?: () => void }) => (
      <div>Paper chat{paperSelection ? ` selection page ${paperSelection.page}` : ""}
        {onReaderClose && <button type="button" onClick={onReaderClose}>Close chat</button>}
        {mocks.showArtifact && <PosterArtifact block={{
          kind: "artifact",
          schema_version: 1,
          scope: "owner",
          publication_id: "reader-poster",
          artifact_id: "reader-artifact",
          version_id: "reader-version",
          identifier: "reader-poster",
          artifact_kind: "posterly",
          title: "Reader poster",
          status: "ready",
          version: 1,
          preview_mime: "image/png",
          source_language: "html",
          gate_status: "passed",
          total_bytes: 1024,
        }} />}
      </div>
    ),
  };
});

import PaperReaderView, { readerToolbarResources } from "@/views/PaperReaderView";
import type { Paper } from "@/lib/api/papers.types";

function renderReader(route = "/pdf/1706.03762") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes><Route path="/pdf/:paperId" element={<PaperReaderView />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PaperReaderView", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.stubEnv("VITE_CHAT_ENABLED", "1");
    vi.stubEnv("VITE_PAPER_READER_CHAT_ENABLED", "1");
    mocks.showArtifact = false;
    mocks.paper = arxivPaper;
    mocks.getAvailability.mockResolvedValue({
      status: "available",
      reason: null,
      expected_recovery_at: null,
      paper_mentions_enabled: true,
      web_search_available: true,
      native_pdf_reader_enabled: true,
      paper_reader_chat_enabled: true,
      paper_reader_selection_enabled: false,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("renders the linked title, PDF, and chat-only workspace", async () => {
    renderReader();

    expect(screen.getByRole("link", { name: /Attention Is All You Need/ }))
      .toHaveAttribute("href", "/paper/1706.03762");
    expect(screen.getByRole("link", { name: "Official repository · 1200 stars" }))
      .toHaveAttribute("href", "https://github.com/attention-is-all-you-need/paper");
    expect(screen.getByRole("link", { name: "Project page" }))
      .toHaveAttribute("href", "https://attention.example/project");
    expect(screen.getByRole("link", { name: "3 HF artifacts" }))
      .toHaveAttribute("href", "https://huggingface.co/papers/1706.03762");
    expect(screen.getByRole("region", { name: "Paper PDF" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Paper PDF" }))
      .toHaveAttribute("data-url", "/paper-assets/arxiv-pdf/1706.03762v7");
    expect(screen.getByRole("region", { name: "Paper PDF" }))
      .toHaveAttribute("data-download-url", "https://arxiv.org/pdf/1706.03762v7");
    fireEvent.click(screen.getByRole("tab", { name: "Chat" }));
    expect(screen.getByText("Paper chat")).toBeVisible();
    expect(screen.queryByText("Notes")).not.toBeInTheDocument();
    await waitFor(() => expect(mocks.getAvailability).toHaveBeenCalled());
  });

  it.each([
    ["http://arxiv.org/pdf/hep-th/9901001v2.pdf", "/paper-assets/arxiv-pdf/hep-th/9901001v2"],
    ["https://www.arxiv.org/pdf/2610.03391", "/paper-assets/arxiv-pdf/2610.03391"],
    ["https://arxiv.org/pdf/2610.03391?download=1", "https://arxiv.org/pdf/2610.03391?download=1"],
    ["https://openreview.net/pdf?id=abc", "https://openreview.net/pdf?id=abc"],
  ])("reads %s through %s", (urlPdf, expected) => {
    mocks.paper = { ...mocks.paper, url_pdf: urlPdf };

    renderReader();

    expect(screen.getByRole("region", { name: "Paper PDF" })).toHaveAttribute("data-url", expected);
  });

  it("loads an archived external PDF by catalog paper ID", () => {
    mocks.paper = {
      id: "109743",
      arxiv_id: null,
      title: "External report",
      source: "external",
      version: "v1",
      source_url: "https://example.com/report.pdf",
      url_pdf: null,
      repositories: [],
      project_pages: [],
    };

    renderReader("/pdf/109743");

    expect(screen.getByRole("link", { name: /External report/ }))
      .toHaveAttribute("href", "/paper/109743");
    expect(screen.getByRole("region", { name: "Paper PDF" }))
      .toHaveAttribute("data-url", "/paper-assets/external/109743/paper.pdf");
  });

  it("reads an HTML-only external paper as Markdown and opens chat once it is ready", async () => {
    let resolveMarkdown: (markdown: string) => void = () => undefined;
    mocks.getPaperWebMarkdown.mockReturnValue(new Promise((resolve) => { resolveMarkdown = resolve; }));
    mocks.paper = {
      id: "123294",
      arxiv_id: null,
      title: "LFM2.5-24B-A2B: Built for Fast On-Device Agents",
      source: "external",
      version: "v1",
      source_url: "https://www.liquid.ai/blog/lfm2-5-24b-a2b",
      url_pdf: null,
      repositories: [],
      project_pages: [],
    };

    renderReader("/pdf/123294");

    expect(await screen.findByText("Preparing a readable version of this page…")).toBeVisible();
    expect(screen.queryByRole("region", { name: "Paper PDF" })).not.toBeInTheDocument();
    expect(screen.getByText("Chat opens once the paper is ready.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open original" }))
      .toHaveAttribute("href", "https://www.liquid.ai/blog/lfm2-5-24b-a2b");

    resolveMarkdown(
      "Title: LFM2.5-24B-A2B\n\nURL Source: https://www.liquid.ai/blog/lfm2-5-24b-a2b\n\n"
      + "Markdown Content:\n\n# LFM2.5-24B-A2B\n\nIt scores **48.09** on LiveClaw.\n",
    );

    expect(await screen.findByRole("heading", { name: "LFM2.5-24B-A2B" })).toBeVisible();
    expect(screen.getByText("48.09")).toBeVisible();
    expect(screen.queryByText(/URL Source/)).not.toBeInTheDocument();
    expect(mocks.getPaperWebMarkdown).toHaveBeenCalledWith("123294");
    fireEvent.click(screen.getByRole("tab", { name: "Chat" }));
    expect(screen.getByText("Paper chat")).toBeVisible();
  });

  it("only accepts an official GitHub repository for the title action", () => {
    const repository = (url: string, isOfficial: boolean) => ({
      id: url,
      paper_id: "42",
      url,
      num_stars: 0,
      is_official: isOfficial,
      source: "test",
    });
    expect(readerToolbarResources({ repositories: [
      repository("https://github.com/community/unofficial", false),
      repository("https://example.com/owner/official", true),
    ] } as Paper).repository).toBeUndefined();
    expect(readerToolbarResources({ repositories: [
      repository("https://github.com/owner/official", true),
    ] } as Paper).repository).toMatchObject({
      href: "https://github.com/owner/official",
      stars: 0,
    });
  });

  it("animates the desktop chat collapse while keeping PDF live resize active", async () => {
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1200);
    renderReader();

    const close = await screen.findByRole("button", { name: "Close chat" });
    const chatPanel = screen.getByRole("tabpanel", { name: "Chat" });

    fireEvent.click(close);

    expect(chatPanel).toHaveClass("is-collapsed");
    expect(chatPanel).toHaveStyle({ width: "0px" });
    expect(screen.getByRole("button", { name: "Open chat" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("region", { name: "Paper PDF" }))
      .toHaveAttribute("data-resize-active", "true");
  });

  it("coalesces desktop divider dragging without width transitions or per-move persistence", async () => {
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1200);
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");
    renderReader();

    const separator = await screen.findByRole("separator", { name: "Resize paper and Chat panels" });
    const workspace = separator.closest<HTMLElement>(".reader-workspace");
    const paperPane = screen.getByRole("tabpanel", { name: "Paper" });
    expect(workspace).not.toBeNull();
    vi.spyOn(workspace!, "getBoundingClientRect").mockReturnValue({
      left: 0,
      width: 1200,
      top: 0,
      right: 1200,
      bottom: 800,
      height: 800,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });
    Object.defineProperty(separator, "setPointerCapture", { value: vi.fn() });

    fireEvent.pointerDown(separator, { pointerId: 1, clientX: 792 });
    expect(workspace).toHaveClass("is-resizing");
    fireEvent.pointerMove(separator, { pointerId: 1, clientX: 840 });

    await waitFor(() => expect(paperPane).toHaveStyle({ width: "70%" }));
    expect(storageSpy).not.toHaveBeenCalledWith("pwc:reader:split-ratio", expect.anything());

    fireEvent.pointerUp(separator, { pointerId: 1, clientX: 840 });
    expect(workspace).not.toHaveClass("is-resizing");
    expect(storageSpy).toHaveBeenCalledWith("pwc:reader:split-ratio", "70");
  });

  it("keeps the public PDF surface but disables chat when the live gate closes", async () => {
    mocks.getAvailability.mockResolvedValueOnce({
      status: "available",
      reason: null,
      expected_recovery_at: null,
      paper_mentions_enabled: true,
      web_search_available: true,
      native_pdf_reader_enabled: true,
      paper_reader_chat_enabled: false,
      paper_reader_selection_enabled: false,
    });
    renderReader();

    expect(screen.getByRole("region", { name: "Paper PDF" })).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "Chat" }));
    expect(await screen.findByText("Chat is not enabled for this preview."))
      .toBeVisible();
  });

  it("keeps selection capture off until the live flag is on", async () => {
    renderReader();
    await waitFor(() => expect(mocks.getAvailability).toHaveBeenCalled());
    expect(screen.getByRole("region", { name: "Paper PDF" }))
      .toHaveAttribute("data-selection-enabled", "false");
  });

  it("restores collapsed desktop chat for a selection without switching the paper tab", async () => {
    mocks.getAvailability.mockResolvedValue({
      status: "available",
      reason: null,
      expected_recovery_at: null,
      paper_mentions_enabled: true,
      web_search_available: true,
      native_pdf_reader_enabled: true,
      paper_reader_chat_enabled: true,
      paper_reader_selection_enabled: true,
    });
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1200);
    renderReader();
    fireEvent.click(await screen.findByRole("button", { name: "Close chat" }));
    fireEvent.click(screen.getByRole("button", { name: "Attach selection" }));
    expect(screen.getByRole("tabpanel", { name: "Chat" })).not.toHaveClass("is-collapsed");
    expect(screen.getByText("Paper chat selection page 4")).toBeVisible();
  });

  it("marks the Chat tab as pending without switching away from the paper", async () => {
    mocks.getAvailability.mockResolvedValue({
      status: "available",
      reason: null,
      expected_recovery_at: null,
      paper_mentions_enabled: true,
      web_search_available: true,
      native_pdf_reader_enabled: true,
      paper_reader_chat_enabled: true,
      paper_reader_selection_enabled: true,
    });
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(500);
    renderReader();
    expect(await screen.findByRole("tab", { name: "Chat" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Attach selection" }));
    expect(screen.getByRole("tab", { name: "Chat, selection attached" })).toBeVisible();
    expect(screen.getByRole("tabpanel", { name: "Paper" })).not.toHaveClass("is-hidden");
    expect(document.getElementById("reader-chat-panel")).toHaveClass("is-hidden");
    expect(document.getElementById("reader-chat-panel")).toHaveAttribute("aria-hidden", "true");
    expect(screen.queryByRole("button", { name: "Close chat", hidden: true })).not.toBeInTheDocument();
  });

  it("docks a third far-right poster pane when PDF, chat, and artifact minima fit", async () => {
    mocks.showArtifact = true;
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1440);
    renderReader();
    fireEvent.click(await screen.findByRole("button", { name: /Reader poster/u }));

    expect(await screen.findByRole("complementary", { name: "Reader poster" })).toBeVisible();
    expect(screen.getByTestId("paper-chat-workspace")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Paper PDF" })).toBeVisible();
    expect(screen.getByText("Paper chat")).toBeVisible();
    expect(screen.getByTestId("paper-chat-workspace").closest("[data-artifact-layout]"))
      .toHaveAttribute("data-artifact-layout", "split");
  });

  it("uses a full-workspace poster dialog below the three-pane breakpoint without unmounting the PDF", async () => {
    mocks.showArtifact = true;
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1100);
    renderReader();
    fireEvent.click(await screen.findByRole("button", { name: /Reader poster/u }));

    expect(await screen.findByRole("dialog", { name: "Reader poster" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Paper PDF" })).toBeInTheDocument();
    expect(screen.getByTestId("paper-chat-workspace").closest("[data-artifact-layout]"))
      .toHaveAttribute("data-artifact-layout", "dialog");
  });
});

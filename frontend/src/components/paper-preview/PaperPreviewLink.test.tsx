import React from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatMarkdown } from "@/components/chat/ChatMarkdown";
import MarkdownText from "@/components/MarkdownText";
import { PaperPreviewLink } from "@/components/paper-preview/PaperPreviewLink";
import type { PaperPreviewData } from "@/components/paper-preview/paperPreviewData";
import type { Paper } from "@/lib/api/papers.types";
import { preloadImage } from "@/lib/imagePreloader";

const mockedGetPaper = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/papers", () => ({ papersApi: { get: mockedGetPaper } }));
vi.mock("@/lib/imagePreloader", () => ({
  preloadImage: vi.fn().mockResolvedValue(undefined),
}));

const mockedPreloadImage = vi.mocked(preloadImage);

const paper: Paper = {
  id: "42",
  arxiv_id: "2501.12326",
  source: "arxiv",
  source_url: "https://arxiv.org/abs/2501.12326",
  url_abs: "https://arxiv.org/abs/2501.12326",
  url_pdf: null,
  thumbnail_url: "/api/thumbnails/paper.png",
  title: "A Useful Paper",
  abstract: "",
  authors: ["Ada Lovelace", "Grace Hopper"],
  published: "2025-01-20",
  conference: "ICLR 2025",
  version: "v1",
  is_latest_version: true,
  citation_count: 123,
  tasks: [{ id: "1", name: "Agents", slug: "agents", level: 0 }],
};

const initialData: PaperPreviewData = {
  routeId: "2501.12326",
  title: "Snapshot Paper",
  arxivId: "2501.12326",
  source: "arxiv",
  sourceUrl: "https://arxiv.org/abs/2501.12326",
  thumbnailUrl: null,
  authors: ["Historical Author"],
  published: "2025-01-20",
  conference: null,
  citationCount: 5,
  tasks: [],
};

function renderWithProviders(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const CurrentPath: React.FC = () => {
  const location = useLocation();
  return <output data-testid="current-path">{location.pathname}</output>;
};

async function hoverLink(name: string) {
  await userEvent.hover(screen.getByRole("link", { name }));
}

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  mockedGetPaper.mockReset();
  mockedPreloadImage.mockClear();
});

describe("PaperPreviewLink", () => {
  it("is a normal anchor before interaction and loads only after opening", async () => {
    let resolvePaper: (value: Paper) => void = () => {};
    mockedGetPaper.mockReturnValue(
      new Promise((resolve) => {
        resolvePaper = resolve;
      }),
    );
    renderWithProviders(
      <PaperPreviewLink routeId="2501.12326">Useful</PaperPreviewLink>,
    );

    const link = screen.getByRole("link", { name: "Useful" });
    expect(link).toHaveAttribute("href", "/paper/2501.12326");
    expect(mockedGetPaper).not.toHaveBeenCalled();

    await hoverLink("Useful");
    expect(await screen.findByText("Loading preview…")).toBeInTheDocument();
    expect(mockedGetPaper).toHaveBeenCalledWith("2501.12326", false);
    resolvePaper(paper);
    expect(await screen.findByText("A Useful Paper")).toBeInTheDocument();
  });

  it("deduplicates repeated paper links through the shared query key", async () => {
    mockedGetPaper.mockResolvedValue(paper);
    renderWithProviders(
      <>
        <PaperPreviewLink routeId="2501.12326">First</PaperPreviewLink>
        <PaperPreviewLink routeId="2501-12326v2">Second</PaperPreviewLink>
      </>,
    );

    await hoverLink("First");
    expect(await screen.findByText("A Useful Paper")).toBeInTheDocument();
    await userEvent.unhover(screen.getByRole("link", { name: "First" }));
    await hoverLink("Second");
    await screen.findByText("A Useful Paper");
    expect(mockedGetPaper).toHaveBeenCalledTimes(1);
  });

  it("renders supplied snapshot metadata without fetching", async () => {
    renderWithProviders(
      <PaperPreviewLink routeId="2501.12326" initialData={initialData}>
        Snapshot
      </PaperPreviewLink>,
    );
    await hoverLink("Snapshot");
    expect(await screen.findByText("Snapshot Paper")).toBeInTheDocument();
    expect(mockedGetPaper).not.toHaveBeenCalled();
  });

  it.each(["404", "network"])(
    "keeps the link usable after a %s preview failure",
    async (failure) => {
      mockedGetPaper.mockRejectedValue(new Error(failure));
      renderWithProviders(
        <PaperPreviewLink routeId="999999">Missing</PaperPreviewLink>,
      );
      await hoverLink("Missing");
      expect(await screen.findByText("Preview unavailable")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Missing" })).toHaveAttribute(
        "href",
        "/paper/999999",
      );
    },
  );

  it("uses the faux thumbnail when the image fails", async () => {
    mockedGetPaper.mockResolvedValue(paper);
    renderWithProviders(
      <PaperPreviewLink routeId="2501.12326">Thumbnail</PaperPreviewLink>,
    );
    await hoverLink("Thumbnail");
    const image = await screen.findByTestId("paper-preview-image");
    fireEvent.error(image);
    expect(await screen.findByTestId("faux-paper-thumb")).toBeInTheDocument();
  });

  it("renders an optional footer once preview data is available", async () => {
    renderWithProviders(
      <PaperPreviewLink
        routeId="2501.12326"
        initialData={initialData}
        previewFooter={() => <button type="button">Jump to reference</button>}
      >
        Cited
      </PaperPreviewLink>,
    );
    screen.getByRole("link", { name: "Cited" }).focus();
    expect(await screen.findByRole("button", { name: "Jump to reference" })).toBeInTheDocument();
  });

  it("opens from keyboard focus and closes with Escape", async () => {
    renderWithProviders(
      <PaperPreviewLink routeId="2501.12326" initialData={initialData}>
        Keyboard
      </PaperPreviewLink>,
    );
    screen.getByRole("link", { name: "Keyboard" }).focus();
    expect(await screen.findByText("Snapshot Paper")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitFor(() =>
      expect(screen.queryByText("Snapshot Paper")).not.toBeInTheDocument(),
    );
  });

  it("does not turn a coarse-pointer tap into a preview-only interaction", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: true,
    } as MediaQueryList);
    renderWithProviders(
      <>
        <PaperPreviewLink routeId="2501.12326">Touch</PaperPreviewLink>
        <CurrentPath />
      </>,
    );
    const link = screen.getByRole("link", { name: "Touch" });
    fireEvent.pointerEnter(link, { pointerType: "touch" });
    fireEvent.click(link);
    expect(mockedGetPaper).not.toHaveBeenCalled();
    expect(screen.queryByText("Loading preview…")).not.toBeInTheDocument();
    expect(screen.getByTestId("current-path")).toHaveTextContent(
      "/paper/2501.12326",
    );
  });
});

describe("Markdown and chat policy", () => {
  it("previews strict internal paper links but never other links", async () => {
    mockedGetPaper.mockResolvedValue(paper);
    renderWithProviders(
      <MarkdownText
        text={
          "[paper](/paper/2501.12326) [task](/tasks/agents) [external](https://example.com/paper/2501.12326)"
        }
      />,
    );

    expect(screen.getByRole("link", { name: "task" })).toHaveAttribute(
      "href",
      "/tasks/agents",
    );
    expect(screen.getByRole("link", { name: "external" })).toHaveAttribute(
      "target",
      "_blank",
    );
    expect(mockedGetPaper).not.toHaveBeenCalled();
    await userEvent.hover(screen.getByRole("link", { name: "task" }));
    await userEvent.hover(screen.getByRole("link", { name: "external" }));
    expect(mockedGetPaper).not.toHaveBeenCalled();
    await hoverLink("paper");
    expect(await screen.findByText("A Useful Paper")).toBeInTheDocument();
    expect(mockedGetPaper).toHaveBeenCalledTimes(1);
  });

  it("keeps invalid chat citations visibly invalid and never fetches them", () => {
    renderWithProviders(
      <ChatMarkdown
        text="[Unknown](paper:2501.12326)"
        papers={{}}
        citations={{}}
      />,
    );
    expect(screen.getByText("Unknown")).toHaveClass("chat-invalid-citation");
    expect(screen.queryByRole("link", { name: "Unknown" })).not.toBeInTheDocument();
    expect(mockedGetPaper).not.toHaveBeenCalled();
  });

  it("drops unresolved internal citation placeholders to plain text", () => {
    renderWithProviders(
      <ChatMarkdown
        text="[DINO](paper:<cfg>)"
        papers={{}}
        citations={{}}
      />,
    );
    expect(screen.getByText("DINO")).toHaveClass("chat-invalid-citation");
    expect(screen.queryByRole("link", { name: "DINO" })).not.toBeInTheDocument();
    expect(screen.queryByText("<cfg>")).not.toBeInTheDocument();
    expect(mockedGetPaper).not.toHaveBeenCalled();
  });

  it.each([
    {
      label: "microsoft/Mage-VL",
      href: "https://huggingface.co/microsoft/Mage-VL",
      kind: "Hugging Face model",
      thumbnail:
        "https://cdn-thumbnails.huggingface.co/social-thumbnails/models/microsoft/Mage-VL.png",
    },
    {
      label: "openai/gsm8k",
      href: "https://huggingface.co/datasets/openai/gsm8k",
      kind: "Hugging Face dataset",
      thumbnail:
        "https://cdn-thumbnails.huggingface.co/social-thumbnails/datasets/openai/gsm8k.png",
    },
  ])("renders and previews a canonical $kind link", async ({
    label,
    href,
    kind,
    thumbnail,
  }) => {
    renderWithProviders(
      <ChatMarkdown
        text={`[${label}](${href})`}
        papers={{}}
        citations={{}}
      />,
    );

    const link = screen.getByRole("link", { name: label });
    expect(link).toHaveAttribute("href", href);
    expect(link).toHaveAttribute("target", "_blank");
    await hoverLink(label);
    expect(mockedPreloadImage).toHaveBeenCalledWith(thumbnail);
    expect(await screen.findByText(kind)).toBeInTheDocument();
    expect(screen.getByTestId("hf-preview-image")).toHaveAttribute(
      "src",
      thumbnail,
    );
  });

  it("renders generic HTTPS chat links in a new tab", () => {
    renderWithProviders(
      <ChatMarkdown
        text={
          "[settings](https://huggingface.co/settings/profile) " +
          "[external](https://example.com/docs) " +
          "Bare: https://patch-policy.github.io/, then text."
        }
        papers={{}}
        citations={{}}
      />,
    );

    for (const [name, href] of [
      ["settings", "https://huggingface.co/settings/profile"],
      ["external", "https://example.com/docs"],
      ["https://patch-policy.github.io/", "https://patch-policy.github.io/"],
    ]) {
      expect(screen.getByRole("link", { name })).toHaveAttribute("href", href);
      expect(screen.getByRole("link", { name })).toHaveAttribute("target", "_blank");
      expect(screen.getByRole("link", { name })).toHaveAttribute(
        "rel",
        "noopener noreferrer",
      );
      expect(screen.getByRole("link", { name })).toHaveClass("chat-external-link");
    }
  });

  it("renders and previews GitHub repository links in a new tab", async () => {
    const href = "https://github.com/google-research/vision_transformer";
    const avatar = "https://avatars.githubusercontent.com/u/43830688?v=4";
    const mockedFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        description: "Vision Transformer and MLP-Mixer architectures",
        stars: 14_200,
        forks: 2_100,
        language: "Jupyter Notebook",
        archived: false,
        avatar_url: avatar,
      }),
    });
    vi.stubGlobal("fetch", mockedFetch);
    renderWithProviders(
      <ChatMarkdown
        text={`[google-research/vision_transformer](${href})`}
        papers={{}}
        citations={{}}
      />,
    );

    const link = screen.getByRole("link", {
      name: "google-research/vision_transformer",
    });
    expect(link).toHaveAttribute("href", href);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveClass("chat-github-link");
    expect(link.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    await hoverLink("google-research/vision_transformer");
    expect(await screen.findByText("GitHub repository")).toBeInTheDocument();
    expect(await screen.findByText("Vision Transformer and MLP-Mixer architectures"))
      .toBeInTheDocument();
    expect(mockedFetch).toHaveBeenCalledWith(
      "/api/v1/github/repositories/google-research/vision_transformer/preview",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByTestId("github-preview-image")).toHaveAttribute(
      "src",
      avatar,
    );
    expect(mockedPreloadImage).toHaveBeenCalledWith(avatar);
  });

  it("warms a nearby GitHub preview and avatar before hover", async () => {
    const href = "https://github.com/google-research/vision_transformer";
    const avatar = "https://avatars.githubusercontent.com/u/43830688?v=4";
    const mockedFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        description: "Vision Transformer",
        stars: 14_200,
        forks: 2_100,
        language: "Jupyter Notebook",
        archived: false,
        avatar_url: avatar,
      }),
    });
    vi.stubGlobal("fetch", mockedFetch);
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(private readonly callback: IntersectionObserverCallback) {}
        observe(element: Element) {
          this.callback(
            [{ isIntersecting: true, target: element } as IntersectionObserverEntry],
            this as unknown as IntersectionObserver,
          );
        }
        disconnect() {}
        unobserve() {}
        takeRecords() { return []; }
        root = null;
        rootMargin = "200px";
        thresholds = [0];
      },
    );

    renderWithProviders(
      <ChatMarkdown
        text={`[google-research/vision_transformer](${href})`}
        papers={{}}
        citations={{}}
      />,
    );

    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockedPreloadImage).toHaveBeenCalledWith(avatar));
    expect(screen.queryByText("GitHub repository")).not.toBeInTheDocument();

    await hoverLink("google-research/vision_transformer");
    expect(await screen.findByText("Vision Transformer")).toBeInTheDocument();
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });

  it("keeps deep GitHub links clickable without a repository preview", async () => {
    const href = "https://github.com/google-research/vision_transformer/issues/1";
    renderWithProviders(
      <ChatMarkdown
        text={`[issue](${href})`}
        papers={{}}
        citations={{}}
      />,
    );

    const link = screen.getByRole("link", { name: "issue" });
    expect(link).toHaveAttribute("href", href);
    await hoverLink("issue");
    expect(screen.queryByText("GitHub repository")).not.toBeInTheDocument();
    expect(mockedPreloadImage).not.toHaveBeenCalled();
  });

  it("renders lookalike GitHub hosts as generic links without GitHub branding", () => {
    renderWithProviders(
      <ChatMarkdown
        text="[fake](https://github.com.example.org/owner/repo)"
        papers={{}}
        citations={{}}
      />,
    );

    const link = screen.getByRole("link", { name: "fake" });
    expect(link).toHaveClass("chat-external-link");
    expect(link).not.toHaveClass("chat-github-link");
    expect(link.querySelector("svg")).not.toBeInTheDocument();
  });

  it("distinguishes authoritative web citations from generic HTTPS links", () => {
    const source = "https://example.com/official-release";
    renderWithProviders(
      <ChatMarkdown
        text={`[official](${source}) [unverified](https://other.example/item)`}
        papers={{}}
        citations={{}}
        webCitations={{
          [source]: {
            kind: "external_source",
            route_id: null,
            url: source,
            source_type: "article",
            provider: "web",
            title: "Official release",
            source_url: null,
          },
        }}
      />,
    );

    expect(screen.getByRole("link", { name: "official" })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
    expect(screen.getByRole("link", { name: "official" })).toHaveClass(
      "chat-web-citation",
    );
    expect(screen.getByRole("link", { name: "unverified" })).toHaveClass(
      "chat-external-link",
    );
    expect(screen.getByRole("link", { name: "unverified" })).not.toHaveClass(
      "chat-web-citation",
    );
  });

  it("previews authoritative web citations with search-supplied metadata", async () => {
    const source = "https://example.com/official-release";
    renderWithProviders(
      <ChatMarkdown
        text={`[official](${source})`}
        papers={{}}
        citations={{}}
        webCitations={{
          [source]: {
            kind: "external_source",
            route_id: null,
            url: source,
            source_type: "article",
            provider: "web",
            title: "Official release",
            excerpt: "A representative release summary.",
            source_url: null,
            thumbnail_url: "https://cdn.example.com/release.png",
            favicon_url: "https://example.com/favicon.ico",
            published: "2026-08-10T00:00:00.000Z",
          },
        }}
      />,
    );

    await hoverLink("official");
    expect(await screen.findByText("Official release")).toBeInTheDocument();
    expect(screen.getByText("example.com")).toBeInTheDocument();
    expect(screen.getByText("2026-08-10")).toBeInTheDocument();
    expect(
      screen.getByText("A representative release summary."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("web-preview-image")).toHaveAttribute(
      "src",
      "https://cdn.example.com/release.png",
    );
  });

  it("renders an S2 paper as a text-only scholarly preview", async () => {
    const source = "https://arxiv.org/abs/2608.01234";
    renderWithProviders(
      <ChatMarkdown
        text={`[external paper](${source})`}
        papers={{}}
        citations={{}}
        webCitations={{
          [source]: {
            kind: "external_source",
            route_id: null,
            url: source,
            source_type: "paper",
            provider: "semantic_scholar",
            title: "A Brand New Paper",
            excerpt: "A concise external abstract.",
            source_url: "https://www.semanticscholar.org/paper/s2-id",
            thumbnail_url: null,
            arxiv_id: "2608.01234",
            semantic_scholar_id: "s2-id",
            authors: ["Ada Lovelace", "Grace Hopper"],
            published: "2026",
            citation_count: 3,
          },
        }}
      />,
    );

    const link = screen.getByRole("link", { name: "external paper" });
    expect(link).toHaveClass("chat-external-paper-citation");
    await hoverLink("external paper");
    expect(await screen.findByText("Semantic Scholar")).toBeInTheDocument();
    expect(screen.getByText("A Brand New Paper")).toBeInTheDocument();
    expect(screen.getByText("Ada Lovelace, Grace Hopper")).toBeInTheDocument();
    expect(screen.getByText("3 citations")).toBeInTheDocument();
    expect(document.querySelector(".external-paper-preview-card img")).toBeNull();
  });
});

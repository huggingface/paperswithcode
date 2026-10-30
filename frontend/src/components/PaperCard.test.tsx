import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { papersApi } from "@/lib/api/papers";
import type { Paper } from "@/lib/api/papers.types";
import { PaperCard } from "@/components/PaperCard";
import type { PaperCardProps } from "@/lib/transform";

const paper: PaperCardProps = {
  id: "2601.18184",
  dbId: "1",
  title: "VibeVoice-ASR Technical Report",
  abstract: "",
  authors: ["Zihliang Peng"],
  tags: [],
  methods: [],
  organizations: [
    {
      name: "Microsoft",
      slug: "microsoft",
      logoUrl: "/api/v1/organizations/microsoft/logo/test.png",
    },
  ],
  citations: 0,
  github: null,
  githubUrl: null,
  project: null,
  date: "Jan 26, 2026",
  publishedIso: "2026-01-26",
  year: 2026,
  thumbnailUrl: null,
  tldr: null,
  version: "v1",
  velocity24h: null,
  hfKind: null,
  hfCount: 0,
  hfUrl: null,
  sotaRanks: [],
};

const renderCard = (showInstitution?: boolean, queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })) => {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PaperCard paper={paper} showInstitution={showInstitution} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("PaperCard organization logos", () => {
  it("links organization logos beside the title by default", () => {
    renderCard();

    const link = screen.getByRole("link", {
      name: "View Microsoft organization",
    });
    expect(link).toHaveAttribute("href", "/orgs/microsoft");
    expect(link.querySelector("img")).toHaveAttribute(
      "src",
      "/api/v1/organizations/microsoft/logo/test.png",
    );
  });

  it("hides organization logos when the feed disables them", () => {
    renderCard(false);

    expect(
      screen.queryByRole("link", { name: "View Microsoft organization" }),
    ).not.toBeInTheDocument();
  });
});

 it("prefetches the detail cache consumed when opening the paper", async () => {
   const client = new QueryClient();
   const response = { id: "1", arxiv_id: paper.id, title: paper.title } as Paper;
   const get = vi.spyOn(papersApi, "get").mockResolvedValue(response);
   renderCard(true, client);
   fireEvent.mouseEnter(screen.getByRole("link", { name: paper.title }));
   await waitFor(() => expect(client.getQueryData(["paper", paper.id])).toEqual(response));
   expect(get).toHaveBeenCalledWith(paper.id, true);
   get.mockRestore();
   client.clear();
 });

describe("PaperCard authors", () => {
  it("links displayed author names that have an author page", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PaperCard
            paper={{
              ...paper,
              authors: ["Ada", "Grace", "Alan", "Barbara"],
              authorIds: ["11", null, "13"],
            }}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("link", { name: "Ada" })).toHaveAttribute("href", "/authors/11");
    expect(screen.queryByRole("link", { name: "Grace" })).not.toBeInTheDocument();
    expect(screen.getByText(/Grace/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Alan" })).toHaveAttribute("href", "/authors/13");
    expect(screen.getByText(/\+1 authors/)).toBeInTheDocument();
  });

  it("shows a Hugging Face avatar before linked author names", () => {
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PaperCard
            paper={{
              ...paper,
              authors: ["Ada Lovelace", "Grace Hopper"],
              authorIds: ["11", "12"],
              authorHfProfiles: [
                { username: "ada", avatarUrl: "https://cdn-avatars.huggingface.co/ada.png" },
                null,
              ],
            }}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const avatars = container.querySelectorAll(".paper-card-author-avatar");
    expect(avatars).toHaveLength(1);
    expect(avatars[0]).toHaveAttribute("src", "https://cdn-avatars.huggingface.co/ada.png");
  });
});

describe("PaperCard thumbnails", () => {
  const renderWithThumbnail = (priority?: boolean) =>
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <PaperCard paper={{ ...paper, thumbnailUrl: "/thumb.png" }} priority={priority} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

  it("loads priority thumbnails eagerly", () => {
    const { container } = renderWithThumbnail(true);
    expect(container.querySelector(".paper-thumb-wrap img")).toHaveAttribute("loading", "eager");
  });

  it("defers other thumbnails until they near the viewport", () => {
    vi.stubGlobal("IntersectionObserver", class {
      observe() {}
      disconnect() {}
    });
    const { container } = renderWithThumbnail();
    vi.unstubAllGlobals();
    expect(container.querySelector(".paper-thumb-wrap")).toBeInTheDocument();
    expect(container.querySelector(".paper-thumb-wrap img")).toBeNull();
  });
});

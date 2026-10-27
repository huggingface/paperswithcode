import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Paper } from "@/lib/api/papers.types";
import { papersApi } from "@/lib/api/papers";
import AuthorDetailView from "@/views/AuthorDetailView";

vi.mock("@/hooks/useIntersectionObserver", () => ({
  useIntersectionObserver: () => ({ targetRef: () => {}, isIntersecting: false }),
}));

const paper: Paper = {
  id: "42",
  arxiv_id: "2607.24653",
  source: "arxiv",
  source_url: "https://arxiv.org/abs/2607.24653",
  url_abs: "https://arxiv.org/abs/2607.24653",
  url_pdf: null,
  title: "Kimi K3",
  abstract: "Technical report.",
  authors: ["Researcher"],
  author_links: [{ id: "7", name: "Researcher", hf_username: "researcher" }],
  published: "2026-07-27",
  version: "v1",
  is_latest_version: true,
  citation_count: 0,
};

afterEach(() => vi.restoreAllMocks());

function renderAuthor(path = "/authors/7") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/authors/:authorId"
            element={<><Link to="/authors/8">Coauthor</Link><AuthorDetailView /></>}
          />
          <Route path="/orgs/:slug" element={<h1>Organization page</h1>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AuthorDetailView", () => {
  it("renders the author's papers as a standard filterable paper feed", async () => {
    vi.spyOn(papersApi, "getAuthor").mockResolvedValue({
      id: "7",
      full_name: "Researcher",
      hf_username: "researcher",
      paper_count: 1,
    });
    vi.spyOn(papersApi, "list").mockResolvedValue({
      count: 1,
      next_page: null,
      previous_page: null,
      results: [paper],
    });

    const { container } = renderAuthor();

    expect(await screen.findByRole("heading", { name: "Researcher" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Kimi K3" })).toHaveAttribute(
      "href",
      "/paper/2607.24653",
    );
    expect(container.querySelector(".paper-card")).not.toBeNull();
    expect(papersApi.getAuthor).toHaveBeenCalledWith("7");
    expect(papersApi.list).toHaveBeenCalledWith(
      expect.objectContaining({ author: "7", order_by: "trending", include_resources: true }),
    );

    fireEvent.click(screen.getByRole("button", { name: "newest" }));
    fireEvent.click(screen.getByRole("button", { name: /Has code/ }));
    await waitFor(() =>
      expect(papersApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ author: "7", order_by: "date_published", has_code: true }),
      ),
    );
  });

  it("shows the linked Hugging Face avatar and profile link", async () => {
    vi.spyOn(papersApi, "getAuthor").mockResolvedValue({
      id: "7",
      full_name: "Researcher",
      hf_username: "researcher",
      hf_avatar_url: "https://cdn-avatars.huggingface.co/researcher.png",
      paper_count: 1,
    });
    vi.spyOn(papersApi, "list").mockResolvedValue({
      count: 1,
      next_page: null,
      previous_page: null,
      results: [paper],
    });

    const { container } = renderAuthor();

    expect(await screen.findByRole("heading", { name: "Researcher" })).toBeInTheDocument();
    expect(container.querySelector(".author-avatar")).toHaveAttribute(
      "src",
      "https://cdn-avatars.huggingface.co/researcher.png",
    );
    expect(screen.getByRole("link", { name: "@researcher on Hugging Face" })).toHaveAttribute(
      "href",
      "https://huggingface.co/researcher",
    );
  });

  it("sends an organization listed as an author to its organization page", async () => {
    vi.spyOn(papersApi, "getAuthor").mockResolvedValue({
      id: "7",
      full_name: "Nvidia",
      organization_slug: "nvidia",
      paper_count: 22,
    });
    vi.spyOn(papersApi, "list").mockResolvedValue({
      count: 1,
      next_page: null,
      previous_page: null,
      results: [paper],
    });

    renderAuthor();

    expect(await screen.findByRole("heading", { name: "Organization page" })).toBeInTheDocument();
  });

  it("links a verified Google Scholar profile", async () => {
    vi.spyOn(papersApi, "getAuthor").mockResolvedValue({
      id: "7",
      full_name: "Researcher",
      hf_username: null,
      google_scholar_id: "VoxU11IAAAAJ",
      paper_count: 1,
    });
    vi.spyOn(papersApi, "list").mockResolvedValue({
      count: 1,
      next_page: null,
      previous_page: null,
      results: [paper],
    });

    renderAuthor();

    expect(await screen.findByRole("link", { name: "Google Scholar ↗" })).toHaveAttribute(
      "href",
      "https://scholar.google.com/citations?user=VoxU11IAAAAJ",
    );
  });

  it("never shows the previous author's papers while another author loads", async () => {
    vi.spyOn(papersApi, "getAuthor").mockImplementation(async (id) => ({
      id,
      full_name: id === "7" ? "Researcher" : "Coauthor Name",
      hf_username: null,
      paper_count: 1,
    }));
    vi.spyOn(papersApi, "list").mockImplementation((params) =>
      params?.author === "7"
        ? Promise.resolve({ count: 1, next_page: null, previous_page: null, results: [paper] })
        : new Promise(() => {}),
    );

    renderAuthor();
    expect(await screen.findByRole("link", { name: "Kimi K3" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "Coauthor" }));
    expect(await screen.findByRole("heading", { name: "Coauthor Name" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Kimi K3" })).not.toBeInTheDocument();
  });
});

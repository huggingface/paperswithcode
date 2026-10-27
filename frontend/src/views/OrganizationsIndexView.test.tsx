import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Organizations } from "@/lib/api/catalog.types";
import { catalogApi } from "@/lib/api/catalog";
import OrganizationsIndexView from "@/views/OrganizationsIndexView";

const payload: Organizations = {
  count: 3,
  results: [
    {
      id: "1",
      name: "Qwen",
      slug: "qwen",
      hf_slug: "Qwen",
      logo_url: "/api/v1/organizations/qwen/logo.webp",
      paper_count: 12,
      is_featured: true,
      display_order: 7,
      organization_trending_score: 4,
      trending_rank: 1,
      first_paper_year: 2023,
      latest_paper_year: 2026,
      top_trending_paper: { id: "10", arxiv_id: "2601.00001", title: "Qwen paper" },
    },
    {
      id: "2",
      name: "Meta AI",
      slug: "facebook",
      hf_slug: "facebook",
      logo_url: "https://huggingface.co/avatar.png",
      paper_count: 40,
      is_featured: true,
      display_order: 11,
      organization_trending_score: 3,
      trending_rank: 2,
      first_paper_year: 2018,
      latest_paper_year: 2026,
      top_trending_paper: { id: "11", title: "Meta paper" },
    },
    {
      id: "3",
      name: "xAI",
      slug: "xai-org",
      hf_slug: "xai-org",
      logo_url: null,
      paper_count: 0,
      is_featured: true,
      display_order: 17,
      organization_trending_score: 0,
      trending_rank: 3,
      top_trending_paper: null,
    },
  ],
};

const Location = () => {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
};

function renderView(initialEntry = "/organizations") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route
            path="/organizations"
            element={
              <>
                <OrganizationsIndexView />
                <Location />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("OrganizationsIndexView", () => {
  it("renders the shared page header and compact cards with canonical full-tile links", async () => {
    vi.spyOn(catalogApi, "organizationIndex").mockResolvedValue(payload);
    renderView();
    expect(
      await screen.findByRole("heading", { name: /AI Organizations/i }),
    ).toBeInTheDocument();
    const qwen = await screen.findByRole("link", {
      name: "Browse 12 Qwen papers",
    });
    expect(qwen).toHaveAttribute("href", "/orgs/qwen");
    expect(qwen.closest(".organizations-grid")).toBeInTheDocument();
    expect(screen.getByText("Qwen paper")).toBeInTheDocument();
    expect(screen.getByText("Publishing 2023–2026")).toBeInTheDocument();
    expect(screen.getByText("No papers indexed yet")).toBeInTheDocument();
    expect(screen.queryByText(/Models|Datasets|Code %|upvotes/i)).not.toBeInTheDocument();
  });

  it("searches HF handles and persists search and sort in the URL", async () => {
    vi.spyOn(catalogApi, "organizationIndex").mockResolvedValue(payload);
    const user = userEvent.setup();
    renderView();
    await screen.findByText("Qwen paper");
    await user.clear(screen.getByRole("searchbox", { name: "Search organizations" }));
    await user.type(
      screen.getByRole("searchbox", { name: "Search organizations" }),
      "facebook",
    );
    expect(screen.getByRole("link", { name: "Browse 40 Meta AI papers" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Browse 12 Qwen papers" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Most papers" }));
    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent(
        "?q=facebook&sort=papers",
      ),
    );
    expect(screen.queryByText("#2")).not.toBeInTheDocument();
  });

  it("uses a styled fallback when an image fails", async () => {
    vi.spyOn(catalogApi, "organizationIndex").mockResolvedValue(payload);
    const view = renderView();
    await screen.findByRole("link", { name: "Browse 12 Qwen papers" });
    const image = view.container.querySelector(
      'img[src="/api/v1/organizations/qwen/logo.webp"]',
    );
    expect(image).not.toBeNull();
    fireEvent.error(image!);
    expect(screen.getAllByText("Q", { selector: ".organization-logo--fallback" })).toHaveLength(1);
  });

  it("shows card skeletons and no stale count while the directory loads", () => {
    vi.spyOn(catalogApi, "organizationIndex").mockReturnValue(new Promise(() => {}));
    const view = renderView();
    expect(screen.getByRole("heading", { name: "Organizations" })).toBeInTheDocument();
    expect(screen.queryByText(/\d+ organizations/)).not.toBeInTheDocument();
    expect(view.container.querySelectorAll(".organization-card-skeleton")).toHaveLength(12);
  });

  it("shows a retryable error", async () => {
    vi.spyOn(catalogApi, "organizationIndex").mockRejectedValue(new Error("boom"));
    renderView();
    expect(await screen.findByText(/Failed to load organizations/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

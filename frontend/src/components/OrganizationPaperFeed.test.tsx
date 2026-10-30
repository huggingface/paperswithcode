import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useParams,
} from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OrganizationPaperFeed } from "@/components/OrganizationPaperFeed";
import { catalogApi } from "@/lib/api/catalog";

const usePaperFeedQuery = vi.fn();

vi.mock("@/components/Icon", () => ({
  Icon: () => <span aria-hidden="true">GitHub</span>,
}));
vi.mock("@/components/PaperCard", () => ({
  PaperCard: () => <article>Paper card</article>,
}));
vi.mock("@/hooks/useIntersectionObserver", () => ({
  useIntersectionObserver: () => ({
    targetRef: { current: null },
    isIntersecting: false,
  }),
}));
vi.mock("@/hooks/usePapers", () => ({
  usePaperFeedQuery: (key: unknown[]) => usePaperFeedQuery(key),
}));

const taxonomy = {
  organization: {
    id: "1",
    name: "NVIDIA",
    slug: "nvidia",
    hf_slug: "nvidia",
    logo_url: "/api/v1/organizations/nvidia/logo.webp",
    paper_count: 3,
    is_featured: true,
    display_order: 1,
  },
  total_paper_count: 3,
  results: [
    {
      id: "1",
      name: "Vision",
      description: null,
      tasks: [
        {
          id: "10",
          name: "Image Classification",
          slug: "image-classification",
          paper_count: 2,
        },
      ],
    },
  ],
};

const RoutedFeed = () => {
  const { orgSlug = "", taskSlug } = useParams();
  return (
    <>
      <OrganizationPaperFeed
        organizationSlug={orgSlug}
        taskSlug={taskSlug}
      />
      <Location />
    </>
  );
};

const Location = () => {
  const location = useLocation();
  return (
    <output data-testid="location">
      {location.pathname}
      {location.search}
    </output>
  );
};

const renderFeed = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter
        initialEntries={["/orgs/nvidia?order_by=date_published"]}
      >
        <Routes>
          <Route path="/orgs/:orgSlug" element={<RoutedFeed />} />
          <Route path="/orgs/:orgSlug/:taskSlug" element={<RoutedFeed />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

beforeEach(() => {
  vi.spyOn(catalogApi, "organizationContributions").mockResolvedValue({
    start_date: "2025-07-31",
    end_date: "2026-07-30",
    total_count: 3,
    results: [
      { date: "2026-07-29", paper_count: 1 },
      { date: "2026-07-30", paper_count: 2 },
    ],
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  usePaperFeedQuery.mockReset();
});

describe("OrganizationPaperFeed task filtering", () => {
  it("selects a task, scopes the route, and preserves the paper sort", async () => {
    vi.spyOn(catalogApi, "getOrganization").mockResolvedValue(
      taxonomy.organization,
    );
    vi.spyOn(catalogApi, "organizationAreasWithTasks").mockResolvedValue(
      taxonomy,
    );
    usePaperFeedQuery.mockReturnValue({
      data: {
        pages: [
          { count: 3, next_page: null, previous_page: null, results: [] },
        ],
      },
      error: null,
      isLoading: false,
      hasNextPage: false,
      isFetchingNextPage: false,
      fetchNextPage: vi.fn(),
    });

    const user = userEvent.setup();
    renderFeed();

    await user.click(
      await screen.findByRole("combobox", {
        name: "Filter papers by task",
      }),
    );
    await user.type(
      screen.getByPlaceholderText("Search organization tasks..."),
      "classification",
    );
    await user.click(
      await screen.findByRole("option", {
        name: /Image Classification.*2 papers/i,
      }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/orgs/nvidia/image-classification?order_by=date_published",
      );
    });
    expect(usePaperFeedQuery).toHaveBeenLastCalledWith([
      "organization-papers-infinite",
      "nvidia",
      "image-classification",
      expect.objectContaining({ order_by: "date_published" }),
    ]);
  });

  it("loads the contribution graph without waiting for organization metadata", async () => {
    vi.spyOn(catalogApi, "getOrganization").mockReturnValue(
      new Promise(() => {}),
    );
    vi.spyOn(catalogApi, "organizationAreasWithTasks").mockReturnValue(
      new Promise(() => {}),
    );
    usePaperFeedQuery.mockReturnValue({
      data: undefined,
      error: null,
      isLoading: true,
      hasNextPage: false,
      isFetchingNextPage: false,
      fetchNextPage: vi.fn(),
    });

    renderFeed();

    expect(
      await screen.findByText("3 papers recorded in the last year"),
    ).toBeVisible();
    expect(catalogApi.organizationContributions).toHaveBeenCalledWith("nvidia");
  });

  it("renders organization metadata without waiting for taxonomy", async () => {
    vi.spyOn(catalogApi, "getOrganization").mockResolvedValue(
      taxonomy.organization,
    );
    vi.spyOn(catalogApi, "organizationAreasWithTasks").mockReturnValue(
      new Promise(() => {}),
    );
    usePaperFeedQuery.mockReturnValue({
      data: {
        pages: [
          { count: 3, next_page: null, previous_page: null, results: [] },
        ],
      },
      error: null,
      isLoading: false,
      hasNextPage: false,
      isFetchingNextPage: false,
      fetchNextPage: vi.fn(),
    });

    renderFeed();

    const heading = await screen.findByRole("heading", { name: "NVIDIA" });
    expect(heading).toBeVisible();
    expect(heading.querySelector("img")).toHaveAttribute(
      "src",
      "/api/v1/organizations/nvidia/logo.webp",
    );
    expect(
      await screen.findByText("3 papers recorded in the last year"),
    ).toBeVisible();
    expect(
      screen.getByRole("img", {
        name: "NVIDIA recorded 3 papers in the last year",
      }),
    ).toBeVisible();
    expect(heading.closest("header")).toContainElement(
      screen.getByRole("img", {
        name: "NVIDIA recorded 3 papers in the last year",
      }),
    );
  });
});

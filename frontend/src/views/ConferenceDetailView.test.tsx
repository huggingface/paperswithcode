import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { catalogApi } from "@/lib/api/catalog";
import ConferenceDetailView from "@/views/ConferenceDetailView";

afterEach(() => vi.restoreAllMocks());

it("links each browse listing that has papers", async () => {
  vi.spyOn(catalogApi, "conferenceAreasWithTasks").mockResolvedValue({
    conference: { id: "1", name: "ICLR 2026", slug: "iclr-2026", start_date: "2026-04-23", end_date: "2026-04-27" },
    total_paper_count: 120,
    oral_paper_count: 10,
    spotlight_paper_count: 0,
    outstanding_paper_count: 2,
    best_paper_finalist_paper_count: 0,
    results: [
      { id: "a", name: "Vision", tasks: [{ id: "t", name: "Image Classification", slug: "image-classification", paper_count: 7 }] },
    ],
  });

  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/conferences/iclr-2026"]}>
        <Routes>
          <Route path="/conferences/:confSlug" element={<ConferenceDetailView />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  const browse = (await screen.findByRole("heading", { name: "Browse papers" })).closest("section")!;
  expect(within(browse).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([
    "/conferences/iclr-2026/all",
    "/conferences/iclr-2026/oral",
    "/conferences/iclr-2026/outstanding",
  ]);
  expect(screen.getByText("April 23–27, 2026")).toBeInTheDocument();
  expect(screen.getByText("1 tasks across 1 areas.")).toBeInTheDocument();
});

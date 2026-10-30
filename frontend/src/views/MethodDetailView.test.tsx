import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { ApiError } from "@/lib/apiTransport";
import { afterEach, describe, expect, it, vi } from "vitest";

import { catalogApi } from "@/lib/api/catalog";
import { papersApi } from "@/lib/api/papers";
import MethodDetailView from "@/views/MethodDetailView";

afterEach(() => vi.restoreAllMocks());

const Location = () => <output data-testid="location">{useLocation().search}</output>;

const renderMethod = (entry = "/methods/world-action-models") =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/methods/:methodSlug" element={<><MethodDetailView /><Location /></>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

const mockMethod = () => {
  vi.spyOn(catalogApi, "getMethod").mockResolvedValue({
    id: "1023",
    slug: "world-action-models",
    name: "World Action Models",
    full_name: "World Action Models (WAMs)",
    source_url: "/paper/2605.12090",
    source_title: "World Action Models: The Next Frontier in Embodied AI",
    introduced_year: 2026,
    paper_count: 0,
  });
  vi.spyOn(catalogApi, "methodTrend").mockRejectedValue(new Error("not needed"));
  vi.spyOn(papersApi, "forMethod").mockResolvedValue({
    count: 0,
    next_page: null,
    previous_page: null,
    results: [],
  });
};

describe("MethodDetailView", () => {
  it("links a native source paper route", async () => {
    mockMethod();
    renderMethod();

    expect(
      await screen.findByRole("link", {
        name: /World Action Models: The Next Frontier in Embodied AI/,
      }),
    ).toHaveAttribute("href", "/paper/2605.12090");
    expect(document.querySelector(".method-hero-grid")).toHaveClass(
      "method-hero-grid--wide-figure",
    );
  });

  it("keeps the paper sort in the shareable URL", async () => {
    mockMethod();
    renderMethod("/methods/world-action-models?order_by=citation_count");

    expect(await screen.findByRole("button", { name: "most cited" })).toHaveClass("active");
    expect(papersApi.forMethod).toHaveBeenCalledWith(
      "world-action-models",
      expect.objectContaining({ order_by: "citation_count", page: 1 }),
    );

    fireEvent.click(screen.getByRole("button", { name: "newest" }));
    await waitFor(() =>
      expect(papersApi.forMethod).toHaveBeenLastCalledWith(
        "world-action-models",
        expect.objectContaining({ order_by: "date_published" }),
      ),
    );
    expect(screen.getByTestId("location")).toHaveTextContent("order_by=date_published");

    fireEvent.click(screen.getByRole("button", { name: "trending" }));
    await waitFor(() => expect(screen.getByTestId("location")).toBeEmptyDOMElement());
  });

  it("shows the 404 page for an unknown method", async () => {
    vi.spyOn(catalogApi, "getMethod").mockRejectedValue(
      new ApiError(new Response("{}", { status: 404, statusText: "Not Found" }), "{}"),
    );
    vi.spyOn(catalogApi, "methodTrend").mockRejectedValue(new Error("not needed"));
    vi.spyOn(papersApi, "forMethod").mockRejectedValue(new Error("not needed"));
    vi.spyOn(console, "error").mockImplementation(() => {});
    renderMethod("/methods/missing");

    expect(await screen.findByRole("heading", { name: "404" })).toBeInTheDocument();
  });
});

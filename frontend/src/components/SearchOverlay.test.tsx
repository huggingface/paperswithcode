import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SearchOverlay from "@/components/SearchOverlay";

const searchPapers = vi.fn();
vi.mock("@/lib/api/papers", () => ({ papersApi: { search: (...args: unknown[]) => searchPapers(...args) } }));
vi.mock("@/lib/api/catalog", () => ({
  catalogApi: {
    listTasks: vi.fn(async () => ({ results: [] })),
    listMethods: vi.fn(async () => ({ results: [] })),
    listDatasets: vi.fn(async () => ({ results: [] })),
  },
}));
vi.mock("@/lib/apiUrl", () => ({ isChatEnabled: () => true }));
vi.mock("@/hooks/useDebounce", () => ({ useDebounce: (value: string) => value }));

const Location = () => <div data-testid="location">{useLocation().pathname}{useLocation().search}</div>;

function renderOverlay(onClose = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <SearchOverlay open onClose={onClose} />
        <Routes>
          <Route path="*" element={<Location />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SearchOverlay paper handoff", () => {
  beforeEach(() => {
    searchPapers.mockReset();
    searchPapers.mockResolvedValue({ results: [], next_page: 2, previous_page: null });
  });

  it("consumes Escape before an earlier page shortcut and removes its handler on unmount", () => {
    const closePage = vi.fn();
    const pageKeydown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) closePage();
    };
    window.addEventListener("keydown", pageKeydown);
    try {
      const closeOverlay = vi.fn();
      const view = renderOverlay(closeOverlay);
      fireEvent.keyDown(screen.getByPlaceholderText(/Search papers/), { key: "Escape" });
      expect(closeOverlay).toHaveBeenCalledOnce();
      expect(closePage).not.toHaveBeenCalled();

      view.unmount();
      fireEvent.keyDown(window, { key: "Escape" });
      expect(closeOverlay).toHaveBeenCalledOnce();
      expect(closePage).toHaveBeenCalledOnce();
    } finally {
      window.removeEventListener("keydown", pageKeydown);
    }
  });

  it("keeps Enter assigned to the assistant", async () => {
    renderOverlay();
    const input = screen.getByPlaceholderText(/Search papers/);
    fireEvent.change(input, { target: { value: "vision & language" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByTestId("location")).toHaveTextContent("/chat?q=vision%20%26%20language");
  });

  it("shows an accessible encoded view-all action with zero previews and no pagination", async () => {
    const user = userEvent.setup();
    renderOverlay();
    await user.type(screen.getByPlaceholderText(/Search papers/), "  vision & language  ");
    const viewAll = await screen.findByRole("button", {
      name: "View all paper results for “vision & language”",
    });
    expect(screen.queryByRole("button", { name: "Previous" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
    await user.click(viewAll);
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(
      "/papers?search=vision%20%26%20language",
    ));
  });
});

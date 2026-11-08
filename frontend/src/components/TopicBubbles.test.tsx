import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TopicBubbles from "@/components/TopicBubbles";
import TopicDialog from "@/components/TopicDialog";
import { catalogApi } from "@/lib/api/catalog";
import { researchApi, type ResearchTopic } from "@/lib/api/research";

const auth = vi.hoisted(() => ({ value: { user: { username: "owner", hf_subject: "1" } as object | null, isLoading: false } }));
vi.mock("@/lib/authContext", () => ({ useAuth: () => auth.value, useOptionalAuth: () => auth.value }));

const renderWithProviders = (ui: React.ReactNode) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={ui} />
        <Route path="/following" element={<div>Following feed</div>} />
      </Routes>
    </MemoryRouter>
  </QueryClientProvider>,
);

beforeEach(() => {
  auth.value = { user: { username: "owner", hf_subject: "1" }, isLoading: false };
});
afterEach(() => vi.restoreAllMocks());

describe("TopicBubbles", () => {
  it("ends the popular topics with an Add topic bubble", async () => {
    vi.spyOn(researchApi, "featuredTopics").mockResolvedValue([
      { id: 7, text: "speculative decoding", label: null, creator: null, followers: 3 },
    ]);
    const onAddTopic = vi.fn();
    renderWithProviders(<TopicBubbles onAddTopic={onAddTopic} />);
    const nav = await screen.findByRole("navigation", { name: "Popular topics" });
    expect(nav.lastElementChild).toBe(screen.getByRole("button", { name: "Add topic" }));
    await userEvent.click(screen.getByRole("button", { name: "Add topic" }));
    expect(onAddTopic).toHaveBeenCalledOnce();
  });

  it("shows Add topic when no topics are featured, and nothing without it", async () => {
    vi.spyOn(researchApi, "featuredTopics").mockResolvedValue([]);
    const { unmount } = renderWithProviders(<TopicBubbles onAddTopic={() => {}} />);
    expect(await screen.findByRole("button", { name: "Add topic" })).toBeInTheDocument();
    unmount();
    const { container } = renderWithProviders(<TopicBubbles />);
    await waitFor(() => expect(researchApi.featuredTopics).toHaveBeenCalledTimes(2));
    expect(container).toBeEmptyDOMElement();
  });
});

describe("TopicDialog afterSavePath", () => {
  beforeEach(() => {
    vi.spyOn(catalogApi, "trendingTasks").mockResolvedValue({ results: [] } as never);
    vi.spyOn(catalogApi, "trendingMethods").mockResolvedValue({ results: [] } as never);
    vi.spyOn(researchApi, "followSuggestions").mockResolvedValue({ authors: [], organizations: [] } as never);
    vi.spyOn(researchApi, "follows").mockResolvedValue([]);
    vi.spyOn(researchApi, "topics").mockResolvedValue([]);
  });

  it("saves a new topic and opens the Following feed", async () => {
    const addTopic = vi.spyOn(researchApi, "addTopic").mockResolvedValue({ id: 1, text: "robot learning" } as ResearchTopic);
    renderWithProviders(<TopicDialog open afterSavePath="/following" onOpenChange={() => {}} />);
    await userEvent.type(await screen.findByLabelText("Research topic"), "robot learning");
    await userEvent.click(screen.getByRole("button", { name: "Follow" }));
    expect(await screen.findByText("Following feed")).toBeInTheDocument();
    expect(addTopic).toHaveBeenCalledWith("robot learning");
  });
});

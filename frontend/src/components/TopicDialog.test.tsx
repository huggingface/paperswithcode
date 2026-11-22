import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TopicDialog from "@/components/TopicDialog";
import { catalogApi } from "@/lib/api/catalog";
import { researchApi, type ResearchTopic } from "@/lib/api/research";
import { ApiError } from "@/lib/apiTransport";
import { useResearchFollows } from "@/lib/researchTopic";

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

describe("TopicDialog afterSavePath", () => {
  beforeEach(() => {
    vi.spyOn(catalogApi, "trendingTasks").mockResolvedValue({ results: [] } as never);
    vi.spyOn(catalogApi, "trendingMethods").mockResolvedValue({ results: [] } as never);
    vi.spyOn(researchApi, "followSuggestions").mockResolvedValue({ authors: [], organizations: [] } as never);
    vi.spyOn(researchApi, "follows").mockResolvedValue([]);
    vi.spyOn(researchApi, "topics").mockResolvedValue([]);
    vi.spyOn(researchApi, "featuredTopics").mockResolvedValue([]);
  });

  it("saves a new topic and opens the Following feed", async () => {
    const addTopic = vi.spyOn(researchApi, "addTopic").mockResolvedValue({ id: 1, text: "robot learning" } as ResearchTopic);
    renderWithProviders(<TopicDialog open afterSavePath="/following" onOpenChange={() => {}} />);
    await userEvent.type(await screen.findByLabelText("Research topic"), "robot learning");
    await userEvent.click(screen.getByRole("button", { name: "Follow" }));
    expect(await screen.findByText("Following feed", { selector: "div" })).toBeInTheDocument();
    expect(addTopic).toHaveBeenCalledWith("robot learning");
  });

  it("lands on the Following feed with the saved follows already loaded", async () => {
    vi.mocked(catalogApi.trendingTasks).mockResolvedValue({ results: [{ id: 5, name: "Robotics", slug: "robotics" }] } as never);
    // The refreshed follows take a network round trip, as in production.
    vi.spyOn(researchApi, "setFollow").mockImplementation(async () => {
      vi.mocked(researchApi.follows).mockImplementation(() => new Promise(resolve => setTimeout(
        () => resolve([{ kind: "task", entity_id: 5, name: "Robotics", url: "/tasks/robotics", created_at: "" }]), 50)));
    });
    // What /following sees on its first render decides whether it shows the empty-account intro.
    const firstSeen: (number | undefined)[] = [];
    function Destination() {
      const follows = useResearchFollows();
      const first = useRef(follows.data?.length);
      firstSeen.push(first.current);
      return <div>Following feed</div>;
    }
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route path="/" element={<TopicDialog open afterSavePath="/following" onOpenChange={() => {}} />} />
            <Route path="/following" element={<Destination />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await userEvent.click(await screen.findByRole("tab", { name: /Tasks, methods/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Robotics/ }));
    await userEvent.click(screen.getByRole("button", { name: "Follow" }));
    expect(await screen.findByText("Following feed", { selector: "div" })).toBeInTheDocument();
    expect(firstSeen[0]).toBe(1);
  });

  it("stays disabled while it waits, and closing it cancels the move to the Following feed", async () => {
    vi.mocked(catalogApi.trendingTasks).mockResolvedValue({ results: [{ id: 5, name: "Robotics", slug: "robotics" }] } as never);
    vi.spyOn(researchApi, "setFollow").mockImplementation(async () => {
      vi.mocked(researchApi.follows).mockImplementation(() => new Promise(resolve => setTimeout(() => resolve([]), 80)));
    });
    function Host() {
      const [open, setOpen] = useState(true);
      return <TopicDialog open={open} afterSavePath="/following" onOpenChange={setOpen} />;
    }
    renderWithProviders(<Host />);
    await userEvent.click(await screen.findByRole("tab", { name: /Tasks, methods/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Robotics/ }));
    await userEvent.click(screen.getByRole("button", { name: "Follow" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled());
    await userEvent.keyboard("{Escape}");
    await new Promise(resolve => setTimeout(resolve, 150));
    expect(screen.queryByText("Following feed")).not.toBeInTheDocument();
  });
});

describe("TopicDialog feed management", () => {
  const topic: ResearchTopic = { id: 1, text: "real-time video generation", label: null, set_at: null, status: "done",
    judged: 1, total: 1, suggestions: [], is_public: true, is_creator: true };
  const other: ResearchTopic = { ...topic, id: 2, text: "speculative decoding", is_creator: false,
    creator: { username: "nielsr", avatar_url: "https://huggingface.co/api/users/nielsr/avatar" } };
  beforeEach(() => {
    vi.spyOn(catalogApi, "trendingTasks").mockResolvedValue({ results: [{ id: "7", name: "Robotics", slug: "robotics" }] } as never);
    vi.spyOn(catalogApi, "trendingMethods").mockResolvedValue({ results: [] } as never);
    vi.spyOn(researchApi, "followSuggestions").mockResolvedValue({ authors: [], organizations: [] } as never);
    vi.spyOn(researchApi, "follows").mockResolvedValue([
      { kind: "benchmark", entity_id: 12, name: "SWE-bench Verified", url: "/benchmark/swe-bench-verified", created_at: "" },
    ]);
    vi.spyOn(researchApi, "topics").mockResolvedValue([topic, other]);
    vi.spyOn(researchApi, "topicMatches").mockResolvedValue([]);
    vi.spyOn(researchApi, "featuredTopics").mockResolvedValue([
      { id: 1, text: "real-time video generation", label: null, creator: null, followers: 4 },
      { id: 23, text: "OCR releases", label: null, followers: 5,
        creator: { username: "nielsr", avatar_url: "https://huggingface.co/api/users/nielsr/avatar" } },
    ]);
  });

  it("links every chip to its page in a new tab, beside its toggle", async () => {
    renderWithProviders(<TopicDialog open onOpenChange={() => {}} />);
    const expectNewTab = async (name: string, href: string) => {
      const link = await screen.findByRole("link", { name });
      expect(link).toHaveAttribute("href", href);
      expect(link).toHaveAttribute("target", "_blank");
      expect(link.closest("button")).toBeNull();
    };
    // Your topics and popular topics are cards whose title links out.
    await expectNewTab("Real-time video generation", "/topics/1-real-time-video-generation");
    await expectNewTab("OCR releases", "/topics/23-ocr-releases");
    await userEvent.click(screen.getByRole("tab", { name: /Tasks, methods/ }));
    await expectNewTab("Open the Robotics page", "/tasks/robotics");
    await expectNewTab("Open the SWE-bench Verified page", "/benchmark/swe-bench-verified");
  });

  it("lists popular benchmarks below trending methods, after the ones already followed", async () => {
    vi.spyOn(researchApi, "followSuggestions").mockResolvedValue({ authors: [], organizations: [], benchmarks: [
      { entity_id: 12, name: "SWE-bench Verified", url: "/benchmark/swe-bench-verified", image_url: null },
      { entity_id: 45, name: "GSM8K", url: "/benchmark/gsm8k", image_url: null },
    ] });
    vi.spyOn(catalogApi, "trendingMethods").mockResolvedValue({ results: [{ id: "3", name: "LoRA", slug: "lora" }] } as never);
    renderWithProviders(<TopicDialog open onOpenChange={() => {}} />);
    await userEvent.click(screen.getByRole("tab", { name: /Tasks, methods/ }));
    const heading = await screen.findByRole("heading", { name: "Popular benchmarks" });
    const headings = screen.getAllByRole("heading", { level: 3 }).map(node => node.textContent);
    expect(headings.indexOf("Popular benchmarks")).toBe(headings.indexOf("Trending methods") + 1);
    const group = within(heading.parentElement!);
    expect(group.getAllByRole("button").map(node => node.textContent)).toEqual(["SWE-bench Verified", "GSM8K"]);
    expect(group.getByRole("button", { name: "SWE-bench Verified" })).toHaveAttribute("aria-pressed", "true");
    expect(group.getByRole("link", { name: "Open the GSM8K page" })).toHaveAttribute("href", "/benchmark/gsm8k");
  });

  it("links to the following feed and closes on the way there", async () => {
    const close = vi.fn();
    renderWithProviders(<TopicDialog open onOpenChange={close} />);
    const link = await screen.findByRole("link", { name: "Following feed" });
    expect(link).toHaveAttribute("href", "/following");
    await userEvent.click(link);
    expect(close).toHaveBeenCalledWith(false);
    expect(await screen.findByText("Following feed", { selector: "div" })).toBeInTheDocument();
  });

  it("offers no feed link to guests", async () => {
    auth.value = { user: null, isLoading: false };
    renderWithProviders(<TopicDialog open onOpenChange={() => {}} />);
    await screen.findByRole("heading", { name: /research feed/ });
    expect(screen.queryByRole("link", { name: "Following feed" })).not.toBeInTheDocument();
  });

  it("names the creator of a followed topic someone else made, not your own", async () => {
    renderWithProviders(<TopicDialog open onOpenChange={() => {}} />);
    const group = (await screen.findByRole("heading", { name: "Your topics" })).parentElement!;
    const card = (name: string) => within(group).getByRole("button", { name }).closest(".home-topic-card")!;
    await within(group).findByRole("button", { name: "Speculative decoding" });
    expect(card("Speculative decoding")).toHaveTextContent("by @nielsr");
    expect(card("Real-time video generation")).not.toHaveTextContent("@");
  });

  it("offers popular topics you do not follow yet, with their creator, and follows them on save", async () => {
    const follow = vi.spyOn(researchApi, "followTopic").mockResolvedValue({ ...topic, id: 23, text: "OCR releases" });
    renderWithProviders(<TopicDialog open onOpenChange={() => {}} />);
    const group = (await screen.findByRole("heading", { name: "Popular topics" })).parentElement!;
    // The topic you already follow is not suggested again.
    expect(within(group).queryByRole("button", { name: /Real-time video generation/ })).not.toBeInTheDocument();
    const card = within(group).getByRole("button", { name: "Follow OCR releases" }).closest("li")!;
    expect(card).toHaveTextContent("by @nielsr");
    expect(card).toHaveTextContent("5 followers");
    fireEvent.click(within(card).getByRole("button", { name: "Follow OCR releases" }));
    fireEvent.click(screen.getByRole("button", { name: "Follow" }));
    await waitFor(() => expect(follow).toHaveBeenCalledWith(23));
  });

  it("offers following the catalog page instead of adding a topic named like it", async () => {
    vi.mocked(researchApi.topicMatches).mockImplementation(async text => text === "harness engineering"
      ? [{ kind: "task", entity_id: 9, name: "Harness Engineering", url: "/tasks/harness-engineering" }] : []);
    const add = vi.spyOn(researchApi, "addTopic");
    const follow = vi.spyOn(researchApi, "setFollow").mockResolvedValue(undefined);
    renderWithProviders(<TopicDialog open onOpenChange={() => {}} />);
    fireEvent.change(await screen.findByRole("textbox", { name: "Research topic" }), { target: { value: "Harness  engineering" } });
    const hint = await screen.findByRole("status");
    expect(hint).toHaveTextContent("already has a task page for “Harness engineering”");
    expect(within(hint).getByRole("link", { name: "Open the Harness Engineering page" })).toHaveAttribute("href", "/tasks/harness-engineering");
    // The topic itself cannot be saved; following the task can.
    expect(screen.getByRole("button", { name: "Follow" })).toBeDisabled();
    fireEvent.click(within(hint).getByRole("button", { name: "Harness Engineering" }));
    fireEvent.click(screen.getByRole("button", { name: "Follow" }));
    await waitFor(() => expect(follow).toHaveBeenCalledWith("task", "9", true));
    expect(add).not.toHaveBeenCalled();
  });

  it("shows the server's refusal only while the box holds the refused text", async () => {
    const body = JSON.stringify({ detail: "“robotics” is already a task; follow Robotics instead" });
    vi.spyOn(researchApi, "addTopic").mockRejectedValue(new ApiError(new Response(body, { status: 409 }), body));
    renderWithProviders(<TopicDialog open onOpenChange={() => {}} />);
    const input = await screen.findByRole("textbox", { name: "Research topic" });
    fireEvent.change(input, { target: { value: "robotics" } });
    fireEvent.click(screen.getByRole("button", { name: "Follow" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("follow Robotics instead.");
    fireEvent.change(input, { target: { value: "robot learning for kitchens" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("rewords a topic and makes it private in one save", async () => {
    const update = vi.spyOn(researchApi, "updateTopic").mockResolvedValue({ ...topic, text: "video world models" });
    const privacy = vi.spyOn(researchApi, "setTopicPublic").mockResolvedValue({ ...topic, is_public: false });
    const onOpenChange = vi.fn();
    renderWithProviders(<TopicDialog open onOpenChange={onOpenChange} />);
    // Topics created by someone else have no visibility switch.
    fireEvent.click(await screen.findByRole("button", { name: "Reword Speculative decoding" }));
    expect(screen.queryByRole("switch", { name: "Public topic" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reword Real-time video generation" }));
    const input = screen.getByRole("textbox", { name: "Research topic" });
    expect(input).toHaveValue("real-time video generation");
    fireEvent.change(input, { target: { value: "video world models" } });
    fireEvent.click(screen.getByRole("switch", { name: "Public topic" }));
    expect(screen.getByText("Private: only you see it")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(update).toHaveBeenCalledWith(1, "video world models"));
    expect(privacy).toHaveBeenCalledWith(1, false);
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("reorders topics with the handle keys and saves the order only on Save", async () => {
    const reorder = vi.spyOn(researchApi, "reorderTopics").mockResolvedValue([other, topic]);
    renderWithProviders(<TopicDialog open onOpenChange={() => {}} />);
    fireEvent.keyDown(await screen.findByRole("button", { name: /^Reorder Speculative decoding/ }), { key: "ArrowUp" });
    expect(reorder).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(reorder).toHaveBeenCalledWith([2, 1]));
  });

  it("drops an unticked topic from the new order, removing it first", async () => {
    const calls: string[] = [];
    vi.spyOn(researchApi, "removeTopic").mockImplementation(async () => { calls.push("remove"); });
    const third = { ...topic, id: 3, text: "robot learning" };
    vi.mocked(researchApi.topics).mockResolvedValue([topic, other, third]);
    const reorder = vi.spyOn(researchApi, "reorderTopics").mockImplementation(async () => { calls.push("reorder"); return [third, other]; });
    renderWithProviders(<TopicDialog open onOpenChange={() => {}} />);
    fireEvent.keyDown(await screen.findByRole("button", { name: /^Reorder Robot learning/ }), { key: "ArrowUp" });
    fireEvent.click(screen.getByRole("button", { name: "Real-time video generation" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(reorder).toHaveBeenCalledWith([3, 2]));
    expect(calls).toEqual(["remove", "reorder"]);
  });
});

import { fireEvent, render as renderElement, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatSessionNavigation } from "./ChatSessionNavigation";
import type { ChatSession } from "@/lib/chatSessions";

const render = (element: ReactElement) => renderElement(<MemoryRouter>{element}</MemoryRouter>);

const props = {
  sessions: [],
  loading: false,
  error: "",
  open: true,
  onClose: vi.fn(),
  onNew: vi.fn(),
  onNavigate: vi.fn(),
  onRename: vi.fn(async () => true),
  onDelete: vi.fn(),
  onDeleteMany: vi.fn(async () => true),
};

describe("ChatSessionNavigation resizing", () => {
  beforeEach(() => localStorage.clear());

  it("restores the saved desktop sidebar width", () => {
    localStorage.setItem("pwc:chat:sidebar-width", "360");

    render(<ChatSessionNavigation {...props} />);

    expect(screen.getByRole("complementary")).toHaveStyle({
      "--chat-sidebar-width": "360px",
    });
    expect(screen.getByRole("separator", { name: "Resize chat history" }))
      .toHaveAttribute("aria-valuenow", "360");
  });

  it("resizes by dragging and saves the width when dragging ends", () => {
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");
    render(<ChatSessionNavigation {...props} />);
    const sidebar = screen.getByRole("complementary");
    const separator = screen.getByRole("separator", { name: "Resize chat history" });
    Object.defineProperty(separator, "setPointerCapture", { value: vi.fn() });

    fireEvent.pointerDown(separator, { pointerId: 1, clientX: 280 });
    fireEvent.pointerMove(separator, { pointerId: 1, clientX: 380 });

    expect(sidebar).toHaveStyle({ "--chat-sidebar-width": "380px" });
    expect(storageSpy).not.toHaveBeenCalledWith("pwc:chat:sidebar-width", expect.anything());

    fireEvent.pointerUp(separator, { pointerId: 1, clientX: 380 });

    expect(storageSpy).toHaveBeenCalledWith("pwc:chat:sidebar-width", "380");
  });

  it("resizes from the keyboard and enforces the supported range", () => {
    render(<ChatSessionNavigation {...props} />);
    const sidebar = screen.getByRole("complementary");
    const separator = screen.getByRole("separator", { name: "Resize chat history" });

    fireEvent.keyDown(separator, { key: "ArrowRight" });
    expect(sidebar).toHaveStyle({ "--chat-sidebar-width": "290px" });
    expect(localStorage.getItem("pwc:chat:sidebar-width")).toBe("290");

    fireEvent.keyDown(separator, { key: "Home" });
    expect(sidebar).toHaveStyle({ "--chat-sidebar-width": "200px" });

    fireEvent.keyDown(separator, { key: "End" });
    expect(sidebar).toHaveStyle({ "--chat-sidebar-width": "480px" });
  });

  it("resets the sidebar width on a double click", () => {
    localStorage.setItem("pwc:chat:sidebar-width", "360");
    render(<ChatSessionNavigation {...props} />);

    fireEvent.doubleClick(screen.getByRole("separator", { name: "Resize chat history" }));

    expect(screen.getByRole("complementary")).toHaveStyle({
      "--chat-sidebar-width": "280px",
    });
    expect(localStorage.getItem("pwc:chat:sidebar-width")).toBe("280");
  });
});

const session = (index: number): ChatSession => ({
  id: `chat-${index}`,
  title: `Chat ${index}`,
  selected_model: "luna",
  created_at: new Date(Date.now() - index * 60_000).toISOString(),
  updated_at: new Date(Date.now() - index * 60_000).toISOString(),
  message_count: 2,
  is_busy: false,
  web_search_enabled: false,
});

describe("ChatSessionNavigation history and MCP showcase", () => {
  const sessions = Array.from({ length: 15 }, (_, index) => session(index));

  it("shows the most recent chats and expands to older ones", () => {
    render(<ChatSessionNavigation {...props} sessions={sessions} />);

    expect(screen.getByText("Chat 11")).toBeInTheDocument();
    expect(screen.queryByText("Chat 12")).not.toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "Show 3 older chats" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);

    expect(screen.getByText("Chat 14")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show less" }));
    expect(screen.queryByText("Chat 14")).not.toBeInTheDocument();
  });

  it("keeps an older active chat visible while collapsed", () => {
    render(<ChatSessionNavigation {...props} sessions={sessions} activeSessionId="chat-14" />);

    expect(screen.getByText("Chat 14")).toBeInTheDocument();
    expect(screen.queryByText("Chat 13")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show 2 older chats" })).toBeInTheDocument();
  });

  it("hides the toggle when every chat fits", () => {
    render(<ChatSessionNavigation {...props} sessions={sessions.slice(0, 12)} />);

    expect(screen.queryByRole("button", { name: /older chat|Show less/ })).not.toBeInTheDocument();
  });

  it("links to the MCP server page", () => {
    render(<ChatSessionNavigation {...props} />);

    expect(screen.getByRole("link", { name: /MCP server/ })).toHaveAttribute("href", "/mcp");
  });

  it("keeps the chat open when an unsaved artifact blocks leaving", () => {
    const block = (event: Event) => event.preventDefault();
    window.addEventListener("pwc:artifact-navigation", block);
    render(<ChatSessionNavigation {...props} />);

    const allowed = fireEvent.click(screen.getByRole("link", { name: /MCP server/ }));
    window.removeEventListener("pwc:artifact-navigation", block);

    expect(allowed).toBe(false);
  });
});

describe("ChatSessionNavigation backdrop", () => {
  it("closes the sidebar when tapping outside it", () => {
    const onClose = vi.fn();
    const { container } = render(<ChatSessionNavigation {...props} onClose={onClose} />);

    fireEvent.click(container.querySelector(".chat-sidebar-backdrop")!);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("renders no backdrop while the sidebar is closed", () => {
    const { container } = render(<ChatSessionNavigation {...props} open={false} />);

    expect(container.querySelector(".chat-sidebar-backdrop")).toBeNull();
  });
});

describe("ChatSessionNavigation bulk selection", () => {
  const sessions = ["a", "b", "c"].map((id, index) => ({
    id,
    title: `Chat ${id}`,
    selected_model: "luna",
    created_at: "2026-11-01T00:00:00Z",
    updated_at: `2026-11-0${3 - index}T00:00:00Z`,
    message_count: 2,
  })) as ChatSession[];
  const row = (title: string) => screen.getByText(title).closest(".chat-session") as HTMLElement;

  it("selects chats with Shift-click and deletes them together", async () => {
    const onNavigate = vi.fn();
    const onDeleteMany = vi.fn(async () => true);
    render(<ChatSessionNavigation {...props} sessions={sessions} onNavigate={onNavigate} onDeleteMany={onDeleteMany} />);

    fireEvent.click(row("Chat a"), { shiftKey: true });
    fireEvent.click(row("Chat c"));
    expect(onNavigate).not.toHaveBeenCalled();
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    expect(row("Chat a")).toHaveAttribute("aria-pressed", "true");
    expect(row("Chat b")).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByRole("button", { name: /Delete$/ }));
    expect(onDeleteMany).toHaveBeenCalledWith(["a", "c"]);
    expect(await screen.findByText("Chat b")).toBeInTheDocument();
    await vi.waitFor(() => expect(screen.queryByRole("toolbar")).not.toBeInTheDocument());
  });

  it("keeps the selection when deletion is cancelled and clears it on Escape", async () => {
    const onDeleteMany = vi.fn(async () => false);
    render(<ChatSessionNavigation {...props} sessions={sessions} onDeleteMany={onDeleteMany} />);

    fireEvent.keyDown(row("Chat b"), { key: "Enter", shiftKey: true });
    fireEvent.click(screen.getByRole("button", { name: /Delete$/ }));
    await vi.waitFor(() => expect(onDeleteMany).toHaveBeenCalledWith(["b"]));
    expect(screen.getByText("1 selected")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
  });

  it("disables the toolbar while a bulk delete is running", async () => {
    let finish: (deleted: boolean) => void = () => undefined;
    const onDeleteMany = vi.fn(() => new Promise<boolean>((resolve) => { finish = resolve; }));
    render(<ChatSessionNavigation {...props} sessions={sessions} onDeleteMany={onDeleteMany} />);

    fireEvent.click(row("Chat a"), { shiftKey: true });
    fireEvent.click(screen.getByRole("button", { name: /Delete$/ }));
    const pending = await screen.findByRole("button", { name: /Deleting/ });
    expect(pending).toBeDisabled();
    fireEvent.click(pending);
    expect(onDeleteMany).toHaveBeenCalledTimes(1);

    finish(true);
    await vi.waitFor(() => expect(screen.queryByRole("toolbar")).not.toBeInTheDocument());
  });

  it("selects every chat between two Shift-clicks", () => {
    const fourSessions = [...sessions, { ...sessions[2], id: "d", title: "Chat d", updated_at: "2026-10-31T00:00:00Z" }];
    render(<ChatSessionNavigation {...props} sessions={fourSessions} />);

    fireEvent.click(row("Chat d"), { shiftKey: true });
    fireEvent.click(row("Chat b"), { shiftKey: true });
    expect(screen.getByText("3 selected")).toBeInTheDocument();
    expect(row("Chat a")).toHaveAttribute("aria-pressed", "false");
    ["Chat b", "Chat c", "Chat d"].forEach((title) => expect(row(title)).toHaveAttribute("aria-pressed", "true"));

    // A plain click deselects one chat; the next range starts from it only once it is selected again.
    fireEvent.click(row("Chat c"));
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    fireEvent.click(row("Chat a"));
    fireEvent.keyDown(row("Chat c"), { key: "Enter", shiftKey: true });
    expect(screen.getByText("4 selected")).toBeInTheDocument();
  });

  it("starts the first Shift-click range at the open chat", () => {
    const fourSessions = [...sessions, { ...sessions[2], id: "d", title: "Chat d", updated_at: "2026-10-31T00:00:00Z" }];
    render(<ChatSessionNavigation {...props} sessions={fourSessions} activeSessionId="d" />);

    fireEvent.click(row("Chat b"), { shiftKey: true });
    expect(screen.getByText("3 selected")).toBeInTheDocument();
    expect(row("Chat a")).toHaveAttribute("aria-pressed", "false");
    ["Chat b", "Chat c", "Chat d"].forEach((title) => expect(row(title)).toHaveAttribute("aria-pressed", "true"));

    // The open chat stays the anchor for the next Shift-click.
    fireEvent.click(row("Chat a"), { shiftKey: true });
    expect(screen.getByText("4 selected")).toBeInTheDocument();
  });

  it("keeps a chat selected when Shift-clicked without a range anchor", () => {
    render(<ChatSessionNavigation {...props} sessions={sessions} />);

    fireEvent.click(row("Chat a"), { shiftKey: true });
    fireEvent.click(row("Chat b"), { shiftKey: true });
    fireEvent.click(row("Chat a"));
    fireEvent.click(row("Chat b"), { shiftKey: true });
    expect(row("Chat b")).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(row("Chat c"), { shiftKey: true });
    expect(screen.getByText("2 selected")).toBeInTheDocument();
  });

  it("deletes the whole selection from a selected chat's trash button", async () => {
    const onDelete = vi.fn();
    const onDeleteMany = vi.fn(async () => true);
    render(<ChatSessionNavigation {...props} sessions={sessions} activeSessionId="a" onDelete={onDelete} onDeleteMany={onDeleteMany} />);

    fireEvent.click(row("Chat c"), { shiftKey: true });
    fireEvent.click(within(row("Chat a")).getByRole("button", { name: "Delete selected conversations" }));
    await vi.waitFor(() => expect(onDeleteMany).toHaveBeenCalledWith(["a", "b", "c"]));
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("navigates on a plain click when nothing is selected", () => {
    const onNavigate = vi.fn();
    render(<ChatSessionNavigation {...props} sessions={sessions} onNavigate={onNavigate} />);

    fireEvent.click(row("Chat b"));
    expect(onNavigate).toHaveBeenCalledWith("b");
  });
});

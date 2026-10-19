import { fireEvent, render as renderElement, screen } from "@testing-library/react";
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
});

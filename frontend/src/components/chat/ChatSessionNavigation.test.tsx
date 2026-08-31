import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatSessionNavigation } from "./ChatSessionNavigation";

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

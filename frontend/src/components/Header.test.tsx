import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Header from "@/components/Header";

const buildFlags = vi.hoisted(() => ({ authDisabled: false, chatEnabled: true }));

vi.mock("@/lib/apiUrl", () => ({
  isAuthDisabled: () => buildFlags.authDisabled,
  isChatEnabled: () => buildFlags.chatEnabled,
}));

vi.mock("@/lib/authContext", () => ({
  useAuth: () => ({ user: null, logout: vi.fn() }),
}));

vi.mock("@/components/HfSignInButton", () => ({
  default: () => <button type="button">Sign in</button>,
}));

beforeEach(() => {
  localStorage.clear();
  buildFlags.authDisabled = false;
  buildFlags.chatEnabled = true;
});
afterEach(() => vi.restoreAllMocks());

describe("Header navigation", () => {
  it("uses the same header layout class on Trending and Chat routes", () => {
    const trending = render(
      <MemoryRouter initialEntries={["/"]}>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );
    expect(document.querySelector("header")).toHaveClass("app-header");
    expect(document.querySelector("header")).not.toHaveClass("app-header-chat");

    trending.unmount();
    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );
    expect(document.querySelector("header")).toHaveClass("app-header");
    expect(document.querySelector("header")).not.toHaveClass("app-header-chat");
  });

  it("places Chat immediately after Trending in desktop and mobile navigation", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );

    const desktopLinks = within(screen.getByRole("navigation")).getAllByRole("link");
    expect(desktopLinks[0]).toHaveAccessibleName("Trending");
    expect(desktopLinks[1]).toHaveAccessibleName("Chat");
    expect(desktopLinks[2]).toHaveAccessibleName("Browse state-of-the-art");
    expect(within(desktopLinks[1]).getByText("New")).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent(
      "New: Papers with Code MCP now available",
    );
    expect(
      within(screen.getByRole("status")).getByRole("link", { name: "MCP" }),
    ).toHaveAttribute("href", "https://github.com/huggingface/pwc-cli#mcp-server");
    expect(within(screen.getByRole("status")).queryByRole("link", { name: "chat" }))
      .not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Open menu" }));
    const mobilePanel = document.querySelector(".mobile-nav-panel");
    expect(mobilePanel).not.toBeNull();
    const mobileLinks = within(mobilePanel as HTMLElement).getAllByRole("link");
    expect(mobileLinks[0]).toHaveAccessibleName("Trending");
    expect(mobileLinks[1]).toHaveAccessibleName("Chat");
    expect(mobileLinks[2]).toHaveAccessibleName("Browse state-of-the-art");
    expect(within(mobileLinks[1]).getByText("New")).toBeVisible();
  });

  it("links Chat to the canonical site on the Hugging Face Space mirror", async () => {
    buildFlags.authDisabled = true;
    buildFlags.chatEnabled = false;
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );

    const desktopChat = within(screen.getByRole("navigation")).getAllByRole("link")[1];
    expect(desktopChat).toHaveAccessibleName("Chat");
    expect(desktopChat).toHaveAttribute("href", "https://paperswithcode.co/chat");
    expect(desktopChat).toHaveAttribute("target", "_blank");

    await user.click(screen.getByRole("button", { name: "Open menu" }));
    const mobilePanel = document.querySelector(".mobile-nav-panel") as HTMLElement;
    const mobileChat = within(mobilePanel).getAllByRole("link")[1];
    expect(mobileChat).toHaveAccessibleName("Chat");
    expect(mobileChat).toHaveAttribute("href", "https://paperswithcode.co/chat");
  });

  it("omits Chat when chat is disabled on the canonical site", () => {
    buildFlags.chatEnabled = false;
    render(
      <MemoryRouter>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );

    expect(
      within(screen.getByRole("navigation")).queryByRole("link", { name: "Chat" }),
    ).not.toBeInTheDocument();
  });

  it("closes the mobile menu with its close button or Escape and restores focus", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><Header onOpenSearch={vi.fn()} /></MemoryRouter>);
    const trigger = screen.getByRole("button", { name: "Open menu" });
    await user.click(trigger);
    expect(screen.getByRole("dialog", { name: "Navigation menu" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Close menu" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    await user.click(trigger);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("slides one shared indicator to the active desktop tab", async () => {
    vi.spyOn(HTMLElement.prototype, "offsetLeft", "get")
      .mockImplementation(function getOffsetLeft(this: HTMLElement) {
        return this.textContent?.includes("Chat") ? 96 : 0;
      });
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get")
      .mockImplementation(function getOffsetWidth(this: HTMLElement) {
        return this.classList.contains("nav-item") ? 64 : 0;
      });
    const user = userEvent.setup();

    const { container } = render(
      <MemoryRouter initialEntries={["/"]}>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );
    const indicator = container.querySelector<HTMLElement>(".nav-indicator");
    expect(indicator).not.toBeNull();
    await waitFor(() => expect(indicator).toHaveStyle({
      transform: "translateX(0px)",
      width: "64px",
    }));

    await user.click(within(screen.getByRole("navigation")).getByRole("link", { name: "Chat" }));
    await waitFor(() => expect(indicator).toHaveStyle({
      transform: "translateX(96px)",
      width: "64px",
    }));
    expect(container.querySelectorAll(".nav-indicator")).toHaveLength(1);
  });

  it("hides the MCP announcement on PDF reader routes", () => {
    render(
      <MemoryRouter initialEntries={["/pdf/2606.03748"]}>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("remembers when the MCP announcement is dismissed", async () => {
    const user = userEvent.setup();
    const firstRender = render(
      <MemoryRouter>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole("button", { name: "Dismiss announcement" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    firstRender.unmount();
    render(
      <MemoryRouter>
        <Header onOpenSearch={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

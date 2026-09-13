import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import App from "@/App";

afterEach(() => vi.restoreAllMocks());

it("routes /mcp to the MCP page before the username catch-all and links it in the footer", async () => {
  window.history.replaceState({}, "", "/mcp");
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
  vi.spyOn(console, "log").mockImplementation(() => undefined);
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 503 }));

  render(<App />);

  expect(
    await screen.findByRole("heading", {
      name: "Use Papers With Code in your AI assistant",
    }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "MCP" })).toHaveAttribute("href", "/mcp");
  expect(screen.queryByText(/User profile/i)).not.toBeInTheDocument();
});

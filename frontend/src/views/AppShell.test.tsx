import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import App from "@/App";
import AppErrorBoundary from "@/components/AppErrorBoundary";

beforeEach(() => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
  vi.spyOn(console, "log").mockImplementation(() => undefined);
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 503 }));
});

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});

it("renders the staging access request without the site chrome", async () => {
  window.history.replaceState({}, "", "/request-access");

  render(<App />);

  expect(await screen.findByRole("heading", { name: "Request access" })).toBeInTheDocument();
  expect(screen.queryByRole("banner")).not.toBeInTheDocument();
  expect(screen.queryByRole("contentinfo")).not.toBeInTheDocument();
});

it("gates /submissions behind the shared admin route", async () => {
  window.history.replaceState({}, "", "/submissions?status=pending");

  render(<App />);

  expect(await screen.findByRole("heading", { name: "Sign in required" })).toBeInTheDocument();
  expect(screen.getByRole("contentinfo")).toBeInTheDocument();
});

function Crash({ crash }: { crash: boolean }) {
  if (crash) throw new Error("boom");
  return <p>recovered</p>;
}

it("clears a route-level render failure when the pathname changes", () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  const { rerender } = render(
    <AppErrorBoundary resetKey="/broken"><Crash crash /></AppErrorBoundary>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("This page could not load");

  rerender(<AppErrorBoundary resetKey="/broken"><Crash crash={false} /></AppErrorBoundary>);
  expect(screen.getByRole("alert")).toBeInTheDocument();

  rerender(<AppErrorBoundary resetKey="/next"><Crash crash={false} /></AppErrorBoundary>);
  expect(screen.getByText("recovered")).toBeInTheDocument();
});

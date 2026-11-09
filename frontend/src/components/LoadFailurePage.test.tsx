import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/apiTransport";
import { loadFailurePage } from "./LoadFailurePage";

const apiError = (status: number) => new ApiError(new Response(null, { status }), "");

function renderFailure(errors: unknown[]) {
  const page = loadFailurePage(errors, "Failed to load this method. Please try again.");
  if (page) render(<MemoryRouter>{page}</MemoryRouter>);
  return page;
}

describe("loadFailurePage", () => {
  it("shows nothing while every request succeeded", () => {
    expect(renderFailure([null, undefined])).toBeNull();
  });

  it("shows the not-found page when any request is a 404", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    renderFailure([apiError(500), apiError(404)]);
    expect(screen.getByRole("heading", { name: "404" })).toBeInTheDocument();
  });

  it("reports a failed load instead of claiming the page does not exist", () => {
    renderFailure([apiError(503)]);
    expect(screen.getByText("Failed to load this method. Please try again.")).toBeInTheDocument();
    expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
  });
});

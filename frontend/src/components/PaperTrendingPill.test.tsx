import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { PaperTrendingPill } from "./PaperTrendingPill";

describe("PaperTrendingPill", () => {
  it("shows the rank and links to the trending feed", () => {
    render(<MemoryRouter><PaperTrendingPill rank={5} /></MemoryRouter>);
    const link = screen.getByRole("link", { name: /#5 in trending this week/ });
    expect(link).toHaveAttribute("href", "/");
    expect(link).toHaveAttribute("title", expect.stringContaining("last 7 days"));
  });
});

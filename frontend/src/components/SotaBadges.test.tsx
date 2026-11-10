import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SotaBadges } from "@/components/SotaBadges";
import type { SotaRank } from "@/lib/transform";

const ranks: SotaRank[] = Array.from({ length: 6 }, (_, i) => ({
  name: `Bench${i}`,
  href: `/benchmark/${i}`,
  rank: 1,
}));

// jsdom has no layout: fake a 60px line where text is 2px per character, so
// only the first couple of benchmarks fit and the rest collapse.
beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(60);
  vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockImplementation(function (
    this: HTMLElement,
  ) {
    return (this.textContent ?? "").length * 2;
  });
});
afterEach(() => vi.restoreAllMocks());

describe("SotaBadges", () => {
  it("expands the collapsed benchmarks in place on the paper page", () => {
    render(
      <MemoryRouter>
        <SotaBadges wrap ranks={ranks} paperHref="/paper/1" />
      </MemoryRouter>,
    );
    const more = screen.getByRole("button", { name: /more/ });
    expect(screen.queryByText("Bench5")).toBeNull();

    fireEvent.click(more);
    for (const r of ranks) expect(screen.getByRole("link", { name: r.name })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /show less/ }));
    expect(screen.queryByText("Bench5")).toBeNull();
  });

  it("links the overflow to the paper on cards", () => {
    render(
      <MemoryRouter>
        <SotaBadges ranks={ranks} paperHref="/paper/1" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: /more/ }).getAttribute("href")).toBe(
      "/paper/1#results",
    );
  });
});

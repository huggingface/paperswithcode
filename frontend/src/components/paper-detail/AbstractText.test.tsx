import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { AbstractMention } from "@/lib/api/papers.types";
import { AbstractText } from "./AbstractText";

const abstract = "We train Diffusion Transformers (DiTs) with GRPO on SWE-bench Verified.";

const mention = (surface: string, entity_type: AbstractMention["entity_type"], slug: string) => {
  const start = abstract.indexOf(surface);
  return { start, end: start + surface.length, surface, entity_type, slug, name: surface };
};

const mentions: AbstractMention[] = [
  mention("GRPO", "method", "grpo"),
  mention("Diffusion Transformers (DiTs)", "method", "diffusion-transformer-dit"),
  mention("SWE-bench Verified", "benchmark", "swe-bench-verified"),
];

function renderAbstract(visibleLength: number | null, items = mentions) {
  const client = new QueryClient();
  const { container } = render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <p>
          <AbstractText abstract={abstract} mentions={items} visibleLength={visibleLength} />
        </p>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return container;
}

describe("AbstractText", () => {
  it("links each mention to its catalog page and keeps the rest as text", () => {
    const container = renderAbstract(null);

    expect(container.textContent).toBe(abstract);
    expect(screen.getByRole("link", { name: "GRPO" }).getAttribute("href")).toBe("/methods/grpo");
    expect(
      screen.getByRole("link", { name: "Diffusion Transformers (DiTs)" }).getAttribute("href"),
    ).toBe("/methods/diffusion-transformer-dit");
    expect(
      screen.getByRole("link", { name: "SWE-bench Verified" }).getAttribute("href"),
    ).toBe("/benchmark/swe-bench-verified");
    expect(screen.getByRole("link", { name: "GRPO" }).getAttribute("target")).toBeNull();
  });

  it("leaves mentions past the collapsed preview unlinked", () => {
    const container = renderAbstract(abstract.indexOf("GRPO") + 2);

    expect(screen.queryByRole("link", { name: "GRPO" })).toBeNull();
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(container.textContent).toBe(`${abstract.slice(0, abstract.indexOf("GRPO") + 2)}…`);
  });

  it("shows the preview sent with the paper without fetching on hover", async () => {
    const withPreview = [
      {
        ...mentions[0],
        preview: { name: "GRPO", description: "Group relative policy optimization.", count: 1401 },
      },
    ];
    renderAbstract(null, withPreview);

    fireEvent.pointerEnter(screen.getByRole("link", { name: "GRPO" }), { pointerType: "mouse" });
    fireEvent.focus(screen.getByRole("link", { name: "GRPO" }));

    expect(await screen.findByText("Group relative policy optimization.")).toBeTruthy();
    expect(screen.getByText("1,401 papers")).toBeTruthy();
  });

  it("ignores a stale mention whose text no longer matches", () => {
    renderAbstract(null, [{ ...mentions[0], surface: "PPO" }]);

    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });
});

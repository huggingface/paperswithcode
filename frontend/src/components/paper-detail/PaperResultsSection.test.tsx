import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { Paper } from "@/lib/api/papers.types";

import { PaperResultsSection } from "./PaperResultsSection";

function renderSection(hiddenClosedSourceCount: number) {
  render(
    <MemoryRouter>
      <PaperResultsSection
        canCopyBadge={false}
        canEdit={false}
        evaluationsByTask={[]}
        evaluationsLoading={false}
        hiddenClosedSourceCount={hiddenClosedSourceCount}
        isAdmin={false}
        onCopyBadge={() => undefined}
        onEdit={() => undefined}
        onRefresh={() => undefined}
        paper={{ id: "131941", title: "Closed model report" } as Paper}
        visibleEvaluationCount={0}
      />
    </MemoryRouter>,
  );
}

describe("PaperResultsSection", () => {
  it("points to settings when every eval is a hidden closed-source result", () => {
    renderSection(3);
    expect(screen.getByText(/No evals shown for this paper/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "settings" })).toHaveAttribute("href", "/settings");
  });

  it("keeps the empty message when the paper has no evals", () => {
    renderSection(0);
    expect(screen.getByText("No benchmark results recorded yet.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "settings" })).not.toBeInTheDocument();
  });
});

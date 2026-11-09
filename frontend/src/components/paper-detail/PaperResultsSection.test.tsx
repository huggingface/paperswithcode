import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Evaluation } from "@/lib/api/evaluations.types";
import type { Paper } from "@/lib/api/papers.types";

import { type EvaluationTaskGroup, PaperResultsSection } from "./PaperResultsSection";

const openGroup: EvaluationTaskGroup = {
  taskId: "1",
  taskName: "Question Answering",
  rows: [{ id: "7", task_id: "1", model_name: "Open model", is_open: true } as Evaluation],
};

function renderSection({
  hiddenClosedSourceCount,
  evaluationsByTask = [],
  onShowClosedSourceEvals = () => undefined,
}: {
  hiddenClosedSourceCount: number;
  evaluationsByTask?: EvaluationTaskGroup[];
  onShowClosedSourceEvals?: () => void;
}) {
  render(
    <MemoryRouter>
      <PaperResultsSection
        canCopyBadge={false}
        canEdit={false}
        evaluationsByTask={evaluationsByTask}
        evaluationsLoading={false}
        hiddenClosedSourceCount={hiddenClosedSourceCount}
        isAdmin={false}
        onCopyBadge={() => undefined}
        onEdit={() => undefined}
        onRefresh={() => undefined}
        onShowClosedSourceEvals={onShowClosedSourceEvals}
        paper={{ id: "131941", title: "Closed model report" } as Paper}
        visibleEvaluationCount={evaluationsByTask.length}
      />
    </MemoryRouter>,
  );
}

describe("PaperResultsSection", () => {
  it("explains hidden closed-source evals with a show button and a settings link", async () => {
    const onShow = vi.fn();
    renderSection({ hiddenClosedSourceCount: 15, onShowClosedSourceEvals: onShow });

    expect(screen.getByText(
      "No evals shown for this paper: all 15 results are from closed-source models.",
    )).toBeInTheDocument();
    expect(screen.queryByText("No benchmark results recorded yet.")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Change in Settings →" }))
      .toHaveAttribute("href", "/settings#closed-source-evals");

    await userEvent.click(screen.getByRole("button", { name: "Show closed-source results" }));
    expect(onShow).toHaveBeenCalledOnce();
  });

  it("notes partially hidden results above the visible ones", () => {
    renderSection({ hiddenClosedSourceCount: 1, evaluationsByTask: [openGroup] });

    expect(screen.getByText("1 closed-source result hidden.")).toBeInTheDocument();
    expect(screen.getByText("Open model")).toBeInTheDocument();
  });

  it("keeps the empty message when the paper has no evals", () => {
    renderSection({ hiddenClosedSourceCount: 0 });

    expect(screen.getByText("No benchmark results recorded yet.")).toBeInTheDocument();
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });
});

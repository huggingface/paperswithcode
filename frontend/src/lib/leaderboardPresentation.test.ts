import { describe, expect, it } from "vitest";
import type { Evaluation } from "@/lib/api/evaluations.types";
import {
  countFittingMetricColumns,
  deriveLeaderboardPresentation,
  type LeaderboardPresentationInput,
} from "./leaderboardPresentation";

function evaluation(
  id: string,
  overrides: Partial<Evaluation> = {},
): Evaluation {
  return {
    id,
    paper_id: id,
    dataset_id: "dataset",
    task_id: "task-a",
    model_name: id,
    metrics: { Accuracy: 90 },
    best_metric: "Accuracy",
    is_open: true,
    uses_additional_data: false,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
    paper_published_date: "2026-01-01",
    ...overrides,
  };
}
function derive(overrides: Partial<LeaderboardPresentationInput> = {}) {
  return deriveLeaderboardPresentation({
    evaluations: [],
    tasks: [
      { id: "task-a", slug: "a", name: "A", level: 0 },
      { id: "task-b", slug: "b", name: "B", level: 0 },
    ],
    configuredMetrics: [],
    hideClosed: false,
    showMoreMetrics: false,
    ready: { evaluations: true, tasks: true, directions: true, metrics: true },
    ...overrides,
  });
}

describe("leaderboard presentation", () => {
  it("shows every metric column that fits and keeps at least one", () => {
    const evaluations = [
      evaluation("one", { best_metric: "I2V", metrics: { I2V: 51, V2V: 61, MSE: 3 } }),
    ];
    expect(derive({ evaluations, fittingMetricCount: 2 }).visibleMetrics).toEqual(["I2V", "V2V"]);
    expect(derive({ evaluations, fittingMetricCount: 0 }).visibleMetrics).toEqual(["I2V"]);
    expect(
      derive({ evaluations, fittingMetricCount: 1, showMoreMetrics: true }).visibleMetrics,
    ).toEqual(["I2V", "V2V", "MSE"]);
    const widths = { fixed: 608, harness: 140, metric: 220 };
    expect(countFittingMetricColumns(1100, widths, false)).toBe(2);
    expect(countFittingMetricColumns(1100, widths, true)).toBe(1);
    expect(countFittingMetricColumns(300, widths, false)).toBe(1);
    // Growing can reserve slack for a scrollbar; shrinking happens
    // immediately, so a scrollbar that appears after the column is shown does
    // not hide it again.
    expect(countFittingMetricColumns(1060, widths, false, 1)).toBe(2);
    expect(countFittingMetricColumns(1060, widths, false, 1, 20)).toBe(1);
    expect(countFittingMetricColumns(1070, widths, false, 1, 20)).toBe(2);
    expect(countFittingMetricColumns(1052, widths, false, 2, 20)).toBe(2);
    expect(countFittingMetricColumns(1040, widths, false, 2, 20)).toBe(1);
  });

  it("resolves highlight before task URL before majority and shares case-insensitive metric selection", () => {
    const evaluations = [
      evaluation("one"),
      evaluation("two"),
      evaluation("highlight", {
        task_id: "task-b",
        best_metric: "Loss",
        metrics: { Loss: 2, Accuracy: 80 },
      }),
    ];
    expect(derive({ evaluations }).currentTaskId).toBe("task-a");
    expect(derive({ evaluations, taskSlug: "b" }).currentTaskId).toBe("task-b");
    const model = derive({
      evaluations,
      taskSlug: "a",
      highlightEvalId: "highlight",
      metric: " accuracy ",
    });
    expect(model.primaryTask?.id).toBe("task-b");
    expect(model.activeMetric).toBe("Accuracy");
    expect(model.visibleMetrics).toEqual(["Accuracy"]);
    expect(
      model.rows.map((row) => [row.evaluation.id, row.rank, row.isHighlighted]),
    ).toEqual([["highlight", 1, true]]);
    expect(model.displayedSota).toBe(80);
    expect(model.chartPoints[0].value).toBe(80);
  });

  it("merges sibling metrics before filtering and uses one population for chart, ranks, coverage and summary", () => {
    const evaluations = [
      evaluation("one", { num_parameters: 100 }),
      evaluation("loss", {
        paper_id: "one",
        model_name: "one",
        best_metric: "Loss",
        metrics: { Loss: 2 },
        num_parameters: 100,
      }),
      evaluation("tie", { metrics: { Loss: 2 }, num_parameters: 200 }),
      evaluation("large", { metrics: { Loss: 1 }, num_parameters: 1000 }),
      evaluation("closed", {
        metrics: { Loss: 0 },
        num_parameters: 100,
        is_open: false,
      }),
      evaluation("unknown", { metrics: { Loss: 0 } }),
    ];
    const model = derive({
      evaluations,
      hideClosed: true,
      parameterBound: 500,
      metric: "Loss",
      directions: { directions: { Loss: "lower_is_better" } },
    });
    expect(model.rows.map((row) => row.rank)).toEqual([1, 1]);
    expect(model.rows[0].evaluation.sourceEvaluationIds).toEqual([
      "one",
      "loss",
    ]);
    expect(model.rows[0].evaluation.metrics).toEqual({ Accuracy: 90, Loss: 2 });
    expect(model.chartPoints.map((point) => point.value)).toEqual([2, 2]);
    expect(model.displayedSota).toBe(2);
    expect(model.hiddenClosedEvals).toHaveLength(1);
    expect(model.parameterCoverage).toEqual({
      parameter_coverage_known: 3,
      parameter_coverage_total: 4,
    });
  });

  it("keeps legacy metric unions and unranked rows, while configured columns constrain the default", () => {
    const evaluations = [
      evaluation("one", {
        best_metric: "Loss",
        metrics: { Loss: 2, Accuracy: 90 },
      }),
      evaluation("missing", { metrics: { Accuracy: 80 } }),
    ];
    const legacy = derive({
      evaluations,
      metric: "Loss",
      showMoreMetrics: true,
    });
    expect(legacy.visibleMetrics).toEqual(["Loss", "Accuracy"]);
    expect(legacy.rows.map((row) => row.rank)).toEqual([1, null]);
    const configured = derive({
      evaluations,
      configuredMetrics: [
        {
          metric_id: "accuracy",
          metric_name: "Accuracy",
          metric_direction: "higher_is_better",
        },
      ],
    });
    expect(configured.activeMetric).toBe("Accuracy");
    expect(configured.allowedMetrics).toEqual(["Accuracy"]);
  });

  it("retains the server summary until dependencies resolve, and never uses it for parameter-filtered views", () => {
    const initialSummary = {
      task_id: "task-a",
      metric: "Accuracy",
      value: 99,
      model_name: "Server model",
      evaluation_id: "server",
    };
    const input = {
      evaluations: [evaluation("one")],
      initialSummary,
      ready: {
        evaluations: true,
        tasks: true,
        directions: true,
        metrics: false,
      },
    };
    expect(derive(input).displayedSota).toBe(99);
    expect(derive(input).isSummaryLoading).toBe(false);
    const filtered = derive({ ...input, parameterBound: 1_000_000_000 });
    expect(filtered.displayedSota).toBeUndefined();
    expect(filtered.isInitialFilteredViewLoading).toBe(true);
    expect(filtered.isSummaryLoading).toBe(true);
    expect(
      derive({ evaluations: input.evaluations, initialSummary }).displayedSota,
    ).toBe(90);
  });

  it("does not wait for configured metrics on datasets without linked tasks", () => {
    const model = derive({
      tasks: [],
      evaluations: [evaluation("one")],
      ready: {
        evaluations: true,
        tasks: true,
        directions: true,
        metrics: false,
      },
    });
    expect(model.displayedSota).toBe(90);
    expect(model.isSummaryLoading).toBe(false);
  });
});

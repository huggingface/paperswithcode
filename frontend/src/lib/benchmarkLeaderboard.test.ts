import { describe, expect, it } from "vitest";

import type { Evaluation } from "./api/evaluations.types";
import {
  computeSeries,
  formatParameterCount,
  filterLeaderboardByParameterCount,
  mergeLeaderboardEvaluations,
  parseParameterFilter,
  parseMetricValue,
} from "./benchmarkLeaderboard";

function evaluation(overrides: Partial<Evaluation> = {}): Evaluation {
  return {
    id: "eval-1",
    paper_id: "paper-1",
    task_id: "task-1",
    dataset_id: "dataset-1",
    model_name: "Model One",
    metrics: { Accuracy: 80 },
    uses_additional_data: false,
    is_open: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    paper_published_date: "2025-01-15",
    ...overrides,
  };
}

describe("benchmark leaderboard model", () => {
  it("parses central metric values without accepting unusable input", () => {
    expect(parseMetricValue("88.55 ± 0.04")).toBe(88.55);
    expect(parseMetricValue(42)).toBe(42);
    expect(parseMetricValue("not reported")).toBeNull();
    expect(parseMetricValue(null)).toBeNull();
  });

  it("merges metric-specific rows for the same model and harness", () => {
    const merged = mergeLeaderboardEvaluations([
      evaluation({ id: "accuracy", best_metric: "Accuracy", best_rank: 1 }),
      evaluation({
        id: "f1",
        best_metric: "F1",
        best_rank: 2,
        metrics: { F1: 75 },
      }),
    ]);

    expect(merged).toHaveLength(1);
    expect(merged[0].metrics).toEqual({ Accuracy: 80, F1: 75 });
    expect(merged[0].sourceEvaluationIds).toEqual(["accuracy", "f1"]);
    expect(merged[0].ranksByMetric).toEqual({ Accuracy: 1, F1: 2 });
  });

  it("keeps only consistent sibling parameter counts displayable", () => {
    const merged = mergeLeaderboardEvaluations([
      evaluation({ id: "one", num_parameters: 1_500_000_000 }),
      evaluation({ id: "two", metrics: { F1: 80 } }),
    ]);
    expect(merged[0].parameterCount).toBe(1_500_000_000);

    const conflicting = mergeLeaderboardEvaluations([
      evaluation({ id: "one", num_parameters: 1_000_000_000 }),
      evaluation({ id: "two", metrics: { F1: 80 }, num_parameters: 2_000_000_000 }),
    ]);
    expect(conflicting[0].parameterCount).toBeNull();
    expect(conflicting[0].hasParameterConflict).toBe(true);
  });

  it("accepts only supported URL bounds and formats up to three significant digits", () => {
    expect(parseParameterFilter("3000000000")).toBe(3_000_000_000);
    expect(parseParameterFilter("2000000000")).toBeUndefined();
    expect(parseParameterFilter("nonsense")).toBeUndefined();
    expect(formatParameterCount(1_234_567_890)).toBe("1.23B");
  });

  it("filters only known, consistent parameter counts using a strict bound", () => {
    const merged = mergeLeaderboardEvaluations([
      evaluation({ id: "small", num_parameters: 999_999_999 }),
      evaluation({ id: "at-bound", paper_id: "paper-2", num_parameters: 1_000_000_000 }),
      evaluation({ id: "unknown", paper_id: "paper-3" }),
      evaluation({ id: "conflict", paper_id: "paper-4", num_parameters: 500_000_000 }),
      evaluation({ id: "conflict-sibling", paper_id: "paper-4", metrics: { F1: 80 }, num_parameters: 600_000_000 }),
    ]);

    expect(filterLeaderboardByParameterCount(merged, undefined)).toEqual(merged);
    expect(filterLeaderboardByParameterCount(merged, 1_000_000_000).map((entry) => entry.id))
      .toEqual(["small"]);
  });

  it("marks only improving values as SOTA for lower-is-better metrics", () => {
    const result = computeSeries([
      evaluation({ id: "first", model_name: "First", metrics: { Error: 20 } }),
      evaluation({
        id: "worse",
        model_name: "Worse",
        metrics: { Error: 25 },
        paper_published_date: "2025-02-15",
      }),
      evaluation({
        id: "best",
        model_name: "Best",
        metrics: { Error: 10 },
        paper_published_date: "2025-03-15",
      }),
    ], "Error", "↓");

    expect(result.points.map((point) => point.isSota)).toEqual([true, false, true]);
    expect(result.sota).toBe(10);
    expect(result.sotaModel).toBe("Best");
  });

  it("plots the paper publication date even when evaluations share an evaluated_on stamp", () => {
    const result = computeSeries([
      evaluation({
        id: "earlier",
        model_name: "Earlier",
        evaluated_on: "2026-09-20",
        paper_published_date: "2025-01-15",
        metrics: { Accuracy: 70 },
      }),
      evaluation({
        id: "later",
        model_name: "Later",
        evaluated_on: "2026-09-20",
        paper_published_date: "2025-06-15",
        metrics: { Accuracy: 90 },
      }),
    ], "Accuracy", "↑");

    expect(result.points.map((point) => point.date)).toEqual(["2025-01-15", "2025-06-15"]);
    expect(result.points.map((point) => point.isSota)).toEqual([true, true]);
  });
});

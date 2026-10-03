import { describe, expect, it } from "vitest";

import {
  mapApiEvaluationsToEditable,
  normalizeEvaluationOperations,
  toDirectEvaluationOperations,
  toPendingEvaluationOperations,
  type EditableEvaluationRow,
} from "./evaluationOperations";

const row = (overrides: Partial<EditableEvaluationRow>): EditableEvaluationRow => ({
  task_id: "3",
  dataset_id: "7",
  model_name: " Model ",
  harness: " verified ",
  metric_name: "Accuracy",
  metric_value: "91.2",
  original_metrics: {},
  original_metric_name: "",
  best_rank: "2",
  num_parameters: " 125000 ",
  hf_model_url: " https://huggingface.co/org/model ",
  is_open: true,
  operation: "create",
  ...overrides,
});

describe("evaluation operation normalization", () => {
  it("normalizes create values once and both transports preserve them", () => {
    const canonical = normalizeEvaluationOperations([row({})], () => true);
    const create = canonical[0];
    if (!create || create.kind !== "create") throw new Error("Expected create operation");

    expect(canonical).toEqual([{
      kind: "create",
      data: {
        task_id: 3,
        dataset_id: 7,
        model_name: "Model",
        harness: "verified",
        metrics: { Accuracy: "91.2" },
        best_metric: "Accuracy",
        best_rank: 2,
        num_parameters: 125000,
        hf_model_url: "https://huggingface.co/org/model",
        is_open: true,
      },
    }]);
    expect(toDirectEvaluationOperations(11, canonical)[0]?.payload).toEqual({
      paper_id: 11,
      ...create.data,
    });
    expect(toPendingEvaluationOperations(canonical)[0]).toEqual({
      op: "create",
      data: create.data,
    });
  });

  it("represents update clears as explicit null fields", () => {
    const canonical = normalizeEvaluationOperations([
      row({
        id: "19",
        operation: "update",
        harness: "",
        num_parameters: "",
        hf_model_url: "  ",
      }),
    ], () => true);

    expect(canonical[0]).toMatchObject({
      kind: "update",
      evaluationId: 19,
      data: { harness: null, num_parameters: null, hf_model_url: null },
    });
    expect(toDirectEvaluationOperations(11, canonical)[0]?.payload).toMatchObject({
      harness: null,
      num_parameters: null,
      hf_model_url: null,
    });
    expect(toPendingEvaluationOperations(canonical)[0]).toMatchObject({
      data: { harness: null, num_parameters: null, hf_model_url: null },
    });
  });

  it("clears unsupported harnesses and omits empty create optionals", () => {
    const canonical = normalizeEvaluationOperations([
      row({ operation: "create", harness: "x", num_parameters: "", hf_model_url: "" }),
      row({ id: "20", operation: "update", harness: "x" }),
    ], () => false);

    expect(canonical[0]).not.toHaveProperty("data.harness");
    expect(canonical[0]).not.toHaveProperty("data.num_parameters");
    expect(canonical[0]).not.toHaveProperty("data.hf_model_url");
    expect(canonical[1]).toHaveProperty("data.harness", null);
  });

  it("preserves delete operations and ignores unchanged or incomplete rows", () => {
    const canonical = normalizeEvaluationOperations([
      row({ id: "21", operation: "delete" }),
      row({ id: "22", operation: "unchanged" }),
      row({ operation: "create", metric_value: "" }),
    ], () => true);

    expect(canonical).toEqual([{ kind: "delete", evaluationId: 21 }]);
    expect(toDirectEvaluationOperations(11, canonical)).toEqual([
      { operation: "delete", evaluation_id: 21 },
    ]);
    expect(toPendingEvaluationOperations(canonical)).toEqual([
      { op: "delete", evaluation_id: 21 },
    ]);
  });
});

const storedEvaluation = {
  id: "19", paper_id: "11", task_id: "3", dataset_id: "7",
  model_name: "Model", metrics: { Accuracy: 0, F1: "88.5", Recall: 90 },
  best_metric: "Accuracy", is_open: true, uses_additional_data: false,
  created_at: "", updated_at: "",
};

function updateDraft(overrides: Partial<EditableEvaluationRow>) {
  const [draft] = mapApiEvaluationsToEditable([storedEvaluation]);
  return { ...draft, operation: "update" as const, ...overrides };
}

describe("lossless evaluation drafts", () => {
  it.each([
    { model_name: "Renamed" },
    { num_parameters: "100" },
    { harness: "New harness" },
    { is_open: false },
  ])("preserves every stored score for metadata edits: %j", (changes) => {
    const operations = normalizeEvaluationOperations([updateDraft(changes)], () => true);
    expect(operations[0]).toMatchObject({ data: { metrics: storedEvaluation.metrics } });
    const [direct] = toDirectEvaluationOperations(11, operations);
    const [pending] = toPendingEvaluationOperations(operations);
    expect(pending).toEqual({ op: "update", evaluation_id: 19, data: direct.payload });
  });

  it("keeps zero visible and round-trips it without coercing other stored scores", () => {
    const draft = updateDraft({});
    expect(draft.metric_value).toBe("0");
    expect(normalizeEvaluationOperations([draft], () => false)[0])
      .toMatchObject({ data: { metrics: { Accuracy: 0, F1: "88.5", Recall: 90 } } });
  });

  it("changes only the selected score", () => {
    const operations = normalizeEvaluationOperations([updateDraft({ metric_value: "1" })], () => false);
    expect(operations[0]).toMatchObject({ data: { metrics: { Accuracy: "1", F1: "88.5", Recall: 90 } } });
    expect(storedEvaluation.metrics.Accuracy).toBe(0);
  });

  it("explicitly replaces a renamed metric while preserving other scores", () => {
    const operations = normalizeEvaluationOperations([
      updateDraft({ metric_name: " Exact match ", metric_value: "5" }),
    ], () => false);
    expect(operations[0]).toMatchObject({ data: {
      metrics: { "Exact match": "5", F1: "88.5", Recall: 90 }, best_metric: "Exact match",
    } });
    expect(operations[0]).not.toHaveProperty("data.metrics.Accuracy");
  });

  it("rejects renaming onto an existing score instead of overwriting it", () => {
    expect(() => normalizeEvaluationOperations([
      updateDraft({ metric_name: "F1" }),
    ], () => false)).toThrow('already has that score');
    expect(storedEvaluation.metrics).toEqual({ Accuracy: 0, F1: "88.5", Recall: 90 });
  });

  it("selects the first stored metric when no best metric is supplied", () => {
    const [draft] = mapApiEvaluationsToEditable([{ ...storedEvaluation, best_metric: undefined }]);
    expect(draft.metric_name).toBe("Accuracy");
    expect(draft.metric_value).toBe("0");
  });
});

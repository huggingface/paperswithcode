import { describe, expect, it } from "vitest";

import {
  mapApiEvaluationsToEditable,
  prepareEvaluationDraft,
  validateEvaluationDraft,
  toDirectEvaluationOperations,
  type EditableEvaluationRow,
} from "./evaluationOperations";

function normalizeEvaluationOperations(...args: Parameters<typeof prepareEvaluationDraft>) {
  const draft = prepareEvaluationDraft(...args);
  if (!draft.valid) throw new Error(draft.errors.map(error => error.message).join("; "));
  return draft.operations;
}

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
    if (!create || create.op !== "create") throw new Error("Expected create operation");

    expect(canonical).toEqual([{
      op: "create",
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
      op: "update",
      evaluation_id: 19,
      data: { harness: null, num_parameters: null, hf_model_url: null },
    });
    expect(toDirectEvaluationOperations(11, canonical)[0]?.payload).toMatchObject({
      harness: null,
      num_parameters: null,
      hf_model_url: null,
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

  it("preserves delete operations and ignores unchanged rows", () => {
    const canonical = normalizeEvaluationOperations([
      row({ id: "21", operation: "delete" }),
      row({ id: "22", operation: "unchanged" }),
    ], () => true);

    expect(canonical).toEqual([{ op: "delete", evaluation_id: 21 }]);
    expect(toDirectEvaluationOperations(11, canonical)).toEqual([
      { operation: "delete", evaluation_id: 21 },
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
    expect(operations[0]).toEqual({ op: "update", evaluation_id: 19, data: direct.payload });
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

describe("whole draft validation", () => {
  it("returns all row/field errors and no serializable operations for a mixed batch", () => {
    const draft = prepareEvaluationDraft([
      row({}), row({ task_id: "", dataset_id: "7x", metric_name: " ", metric_value: " " }),
    ], () => true);
    expect(draft).toEqual({ valid: false, errors: [
      { rowIndex: 1, field: "task_id", message: "Select a valid task." },
      { rowIndex: 1, field: "dataset_id", message: "Select a valid dataset." },
      { rowIndex: 1, field: "metric_name", message: "Select a metric." },
      { rowIndex: 1, field: "metric_value", message: "Enter a metric value." },
    ] });
    expect(draft).not.toHaveProperty("operations");
  });

  it.each(["", "0", "-1", "3.1", "3x", "Infinity", "9007199254740992"])("rejects invalid identifiers: %s", id => {
    expect(validateEvaluationDraft([row({ task_id: id, dataset_id: id })])).toHaveLength(2);
    expect(validateEvaluationDraft([row({ operation: "update", id })])).toHaveLength(1);
    expect(validateEvaluationDraft([row({ operation: "delete", id })])).toHaveLength(1);
  });

  it("ignores unchanged incomplete rows and only requires an ID for deletion", () => {
    expect(prepareEvaluationDraft([
      row({ operation: "unchanged", metric_name: "", metric_value: "", task_id: "" }),
      row({ operation: "delete", id: "9", task_id: "", dataset_id: "", metric_value: "" }),
    ], () => false)).toEqual({ valid: true, operations: [{ op: "delete", evaluation_id: 9 }] });
    expect(prepareEvaluationDraft([row({ operation: "unchanged" })], () => false))
      .toEqual({ valid: true, operations: [] });
  });

  it("accepts zero and formatted scores without imposing a new numeric contract", () => {
    expect(validateEvaluationDraft([row({ metric_value: "0" }), row({ metric_value: "91 ± 2" })])).toEqual([]);
  });
  it.each(["abc", "1.5", "Infinity"])("rejects invalid optional integer metadata: %s", value => {
    expect(validateEvaluationDraft([row({ best_rank: value, num_parameters: value })]).map(error => error.field))
      .toEqual(["best_rank", "num_parameters"]);
  });

  it("rejects negative parameter counts and accepts blank metadata or zero", () => {
    expect(validateEvaluationDraft([row({ num_parameters: "-1" })])[0]?.field).toBe("num_parameters");
    expect(validateEvaluationDraft([row({ num_parameters: "0", best_rank: "" }), row({ num_parameters: "" })])).toEqual([]);
  });

});

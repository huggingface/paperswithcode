import type { Evaluation } from "./api/evaluations.types";
import type { EvaluationData, PendingEvaluationOperation } from "./pendingEdits";

export interface EditableEvaluationRow {
  id?: string;
  task_id: string;
  dataset_id: string;
  model_name: string;
  harness: string;
  metric_name: string;
  metric_value: string;
  original_metrics: Evaluation["metrics"];
  original_metric_name: string;
  best_rank?: string;
  num_parameters: string;
  hf_model_url: string;
  is_open: boolean;
  operation: "create" | "update" | "delete" | "unchanged";
}

/** Keep the full score dictionary while exposing one selected score to the editor. */
export function mapApiEvaluationsToEditable(evaluations: Evaluation[]): EditableEvaluationRow[] {
  return evaluations.map(evaluation => {
    const metricName = evaluation.best_metric || Object.keys(evaluation.metrics)[0] || "";
    return {
      id: evaluation.id,
      task_id: evaluation.task_id,
      dataset_id: evaluation.dataset_id,
      model_name: evaluation.model_name || "",
      harness: evaluation.harness || "",
      metric_name: metricName,
      metric_value: String(evaluation.metrics[metricName] ?? ""),
      original_metrics: { ...evaluation.metrics },
      original_metric_name: metricName,
      best_rank: evaluation.best_rank != null ? String(evaluation.best_rank) : "",
      num_parameters: evaluation.num_parameters != null ? String(evaluation.num_parameters) : "",
      hf_model_url: evaluation.hf_model_url || "",
      is_open: evaluation.is_open !== false,
      operation: "unchanged",
    };
  });
}

function editedMetrics(row: EditableEvaluationRow, metricName: string): Evaluation["metrics"] {
  const metrics = { ...row.original_metrics };
  const originalValue = metrics[row.original_metric_name];
  // Renaming replaces the selected metric, leaving every other score intact.
  if (row.original_metric_name !== metricName) delete metrics[row.original_metric_name];
  metrics[metricName] = originalValue != null && row.metric_value === String(originalValue)
    ? originalValue
    : row.metric_value;
  return metrics;
}

/** Wire shape of `POST /evaluations/batch`. */
export type DirectEvaluationOperation = {
  operation: "create" | "update" | "delete";
  evaluation_id?: number;
  payload?: Record<string, unknown>;
};

type SupportsHarness = (taskId: string, datasetId: string) => boolean;

function optionalInteger(value: string | undefined): number | undefined {
  const trimmed = value?.trim();
  return trimmed ? Number(trimmed) : undefined;
}

function nullableNonNegativeInteger(value: string): number | null {
  const trimmed = value.trim();
  return trimmed ? Number(trimmed) : null;
}

function nullableString(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

export interface EvaluationDraftError {
  rowIndex: number;
  field: "id" | "task_id" | "dataset_id" | "metric_name" | "metric_value" | "best_rank" | "num_parameters";
  message: string;
}

function isIdentifier(value: string | undefined): boolean {
  return Boolean(value && /^\d+$/.test(value.trim()) && Number.isSafeInteger(Number(value)) && Number(value) > 0);
}

export function validateEvaluationDraft(rows: EditableEvaluationRow[]): EvaluationDraftError[] {
  const errors: EvaluationDraftError[] = [];
  rows.forEach((row, rowIndex) => {
    if (row.operation === "unchanged") return;
    const add = (field: EvaluationDraftError["field"], message: string) => {
      errors.push({ rowIndex, field, message });
    };
    if (row.operation !== "create" && !isIdentifier(row.id)) {
      add("id", "This result has no valid evaluation ID. Reload the paper before editing it.");
    }
    if (row.operation === "delete") return;
    if (!isIdentifier(row.task_id)) add("task_id", "Select a valid task.");
    if (!isIdentifier(row.dataset_id)) add("dataset_id", "Select a valid dataset.");
    const metricName = row.metric_name.trim();
    if (!metricName) add("metric_name", "Select a metric.");
    else if (metricName !== row.original_metric_name && Object.prototype.hasOwnProperty.call(row.original_metrics, metricName)) {
      add("metric_name", `Cannot rename a metric to "${metricName}": this evaluation already has that score.`);
    }
    if (row.best_rank?.trim() && !Number.isSafeInteger(Number(row.best_rank))) {
      add("best_rank", "Enter a whole-number rank.");
    }
    if (row.num_parameters.trim() && (!Number.isSafeInteger(Number(row.num_parameters)) || Number(row.num_parameters) < 0)) {
      add("num_parameters", "Enter a non-negative whole-number parameter count.");
    }
    // Scores may be formatted strings (for example confidence intervals), not just numbers.
    if (!row.metric_value.trim()) add("metric_value", "Enter a metric value.");
  });
  return errors;
}

export type PreparedEvaluationDraft =
  | { valid: false; errors: EvaluationDraftError[] }
  | { valid: true; operations: PendingEvaluationOperation[] };

export function prepareEvaluationDraft(
  rows: EditableEvaluationRow[],
  supportsHarness: SupportsHarness,
): PreparedEvaluationDraft {
  const errors = validateEvaluationDraft(rows);
  if (errors.length) return { valid: false, errors };
  return { valid: true, operations: normalizeEvaluationOperations(rows, supportsHarness) };
}

function normalizeEvaluationOperations(
  rows: EditableEvaluationRow[],
  supportsHarness: SupportsHarness,
): PendingEvaluationOperation[] {
  const operations: PendingEvaluationOperation[] = [];
  for (const row of rows) {
    if (row.operation === "delete") {
      operations.push({ op: "delete", evaluation_id: Number(row.id) });
      continue;
    }
    if (row.operation !== "create" && row.operation !== "update") continue;

    const metricName = row.metric_name.trim();

    const harnessSupported = supportsHarness(row.task_id, row.dataset_id);
    const common: EvaluationData = {
      task_id: Number(row.task_id),
      dataset_id: Number(row.dataset_id),
      metrics: editedMetrics(row, metricName),
      best_metric: metricName,
      is_open: row.is_open,
    };
    const modelName = row.model_name.trim();
    const bestRank = optionalInteger(row.best_rank);

    if (row.operation === "create") {
      const numParameters = nullableNonNegativeInteger(row.num_parameters);
      const modelUrl = nullableString(row.hf_model_url);
      operations.push({
        op: "create",
        data: {
          ...common,
          ...(modelName ? { model_name: modelName } : {}),
          ...(harnessSupported && row.harness.trim() ? { harness: row.harness.trim() } : {}),
          ...(bestRank !== undefined ? { best_rank: bestRank } : {}),
          ...(numParameters !== null ? { num_parameters: numParameters } : {}),
          ...(modelUrl !== null ? { hf_model_url: modelUrl } : {}),
        },
      });
      continue;
    }

    operations.push({
      op: "update",
      evaluation_id: Number(row.id),
      data: {
        ...common,
        ...(modelName ? { model_name: modelName } : {}),
        harness: harnessSupported ? nullableString(row.harness) : null,
        ...(bestRank !== undefined ? { best_rank: bestRank } : {}),
        num_parameters: nullableNonNegativeInteger(row.num_parameters),
        hf_model_url: nullableString(row.hf_model_url),
      },
    });
  }
  return operations;
}

export function toDirectEvaluationOperations(
  paperId: number,
  operations: PendingEvaluationOperation[],
): DirectEvaluationOperation[] {
  return operations.map((operation) => {
    switch (operation.op) {
      case "delete":
        return { operation: "delete", evaluation_id: operation.evaluation_id };
      case "update":
        return { operation: "update", evaluation_id: operation.evaluation_id, payload: operation.data };
      case "create":
        return { operation: "create", payload: { paper_id: paperId, ...operation.data } };
    }
  });
}

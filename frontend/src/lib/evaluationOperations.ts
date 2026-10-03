import type { Evaluation } from "./api/evaluations.types";

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
  operation?: "create" | "update" | "delete" | "unchanged";
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
  if (row.original_metric_name !== metricName && Object.prototype.hasOwnProperty.call(metrics, metricName)) {
    throw new Error(`Cannot rename a metric to "${metricName}": this evaluation already has that score.`);
  }
  // Renaming replaces the selected metric, leaving every other score intact.
  if (row.original_metric_name !== metricName) delete metrics[row.original_metric_name];
  metrics[metricName] = originalValue != null && row.metric_value === String(originalValue)
    ? originalValue
    : row.metric_value;
  return metrics;
}

interface EvaluationData extends Record<string, unknown> {
  task_id: number;
  dataset_id: number;
  model_name?: string;
  harness?: string | null;
  metrics: Evaluation["metrics"];
  best_metric: string;
  best_rank?: number;
  num_parameters?: number | null;
  hf_model_url?: string | null;
  is_open: boolean;
}

export type EvaluationOperation =
  | { kind: "create"; data: EvaluationData }
  | { kind: "update"; evaluationId: number; data: EvaluationData }
  | { kind: "delete"; evaluationId: number };

export type DirectEvaluationOperation = {
  operation: "create" | "update" | "delete";
  evaluation_id?: number;
  payload?: Record<string, unknown>;
};

export type PendingEvaluationOperation =
  | { op: "create"; data: EvaluationData }
  | { op: "update"; evaluation_id: number; data: EvaluationData }
  | { op: "delete"; evaluation_id: number };

type SupportsHarness = (taskId: string, datasetId: string) => boolean;

function optionalInteger(value: string | undefined): number | undefined {
  const trimmed = value?.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : undefined;
}

function nullableNonNegativeInteger(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed >= 0 ? Math.trunc(parsed) : null;
}

function nullableString(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

function identifiers(row: EditableEvaluationRow): { taskId: number; datasetId: number } | null {
  const taskId = Number.parseInt(row.task_id, 10);
  const datasetId = Number.parseInt(row.dataset_id, 10);
  return Number.isFinite(taskId) && Number.isFinite(datasetId)
    ? { taskId, datasetId }
    : null;
}

export function normalizeEvaluationOperations(
  rows: EditableEvaluationRow[],
  supportsHarness: SupportsHarness,
): EvaluationOperation[] {
  const operations: EvaluationOperation[] = [];
  for (const row of rows) {
    if (row.operation === "delete" && row.id) {
      operations.push({ kind: "delete", evaluationId: Number.parseInt(row.id, 10) });
      continue;
    }
    if (row.operation !== "create" && row.operation !== "update") continue;

    const ids = identifiers(row);
    const metricName = row.metric_name.trim();
    if (!ids || !metricName || !row.metric_value.trim()) continue;

    const harnessSupported = supportsHarness(row.task_id, row.dataset_id);
    const common: EvaluationData = {
      task_id: ids.taskId,
      dataset_id: ids.datasetId,
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
        kind: "create",
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

    if (!row.id) continue;
    operations.push({
      kind: "update",
      evaluationId: Number.parseInt(row.id, 10),
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
  operations: EvaluationOperation[],
): DirectEvaluationOperation[] {
  return operations.map((operation) => {
    if (operation.kind === "delete") {
      return { operation: "delete", evaluation_id: operation.evaluationId };
    }
    return {
      operation: operation.kind,
      ...(operation.kind === "update" ? { evaluation_id: operation.evaluationId } : {}),
      payload: operation.kind === "create"
        ? { paper_id: paperId, ...operation.data }
        : operation.data,
    };
  });
}

export function toPendingEvaluationOperations(
  operations: EvaluationOperation[],
): PendingEvaluationOperation[] {
  return operations.map((operation) => {
    if (operation.kind === "delete") {
      return { op: "delete", evaluation_id: operation.evaluationId };
    }
    if (operation.kind === "update") {
      return {
        op: "update",
        evaluation_id: operation.evaluationId,
        data: operation.data,
      };
    }
    return { op: "create", data: operation.data };
  });
}

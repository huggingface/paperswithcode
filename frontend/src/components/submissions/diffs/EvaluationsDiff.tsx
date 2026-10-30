import React from "react";
import { useQueries } from "@tanstack/react-query";

import { cn } from "@/lib/utils";
import { catalogApi } from "@/lib/api/catalog";
import type { EvaluationSnapshot, PendingEditOf } from "@/lib/pendingEdits";
import { EmptyInline, Field } from "./shared";
import { catalogQueryKeys } from "@/lib/api/queryKeys";

function useCatalogNames(
  kind: "task" | "dataset",
  ids: number[],
  fetchEntity: (id: string) => Promise<{ id: string; name: string }>,
): Map<number, string> {
  return useQueries({
    queries: ids.map((id) => ({
      queryKey: catalogQueryKeys[kind](String(id)),
      queryFn: () => fetchEntity(String(id)),
      staleTime: 5 * 60 * 1000,
    })),
    combine: (results) => new Map(
      results.flatMap(({ data }) => (data ? [[Number(data.id), data.name] as const] : [])),
    ),
  });
}

export function EvaluationsDiff({ edit }: { edit: PendingEditOf<"evaluations"> }) {
  const currentEvaluations = React.useMemo(
    () => edit.current_payload?.evaluations ?? [],
    [edit.current_payload],
  );
  const operations = edit.proposed_payload.operations;

  const { taskIds, datasetIds } = React.useMemo(() => {
    const rows = [
      ...currentEvaluations,
      ...operations.flatMap((operation) => (operation.op === "delete" ? [] : [operation.data])),
    ];
    const ids = (field: "task_id" | "dataset_id") =>
      Array.from(new Set(rows.flatMap((row) => (row[field] ? [row[field]] : []))));
    return { taskIds: ids("task_id"), datasetIds: ids("dataset_id") };
  }, [currentEvaluations, operations]);

  const taskNames = useCatalogNames("task", taskIds, (id) => catalogApi.getTask(id));
  const datasetNames = useCatalogNames("dataset", datasetIds, (id) => catalogApi.getDataset(id));

  const currentById = new Map(
    currentEvaluations
      .filter((evaluation) => evaluation.id != null)
      .map((evaluation) => [evaluation.id, evaluation]),
  );

  if (operations.length === 0) {
    return <EmptyInline>No evaluation operations in this payload.</EmptyInline>;
  }

  return (
    <div className="submission-eval-list">
      {operations.map((operation, index) => {
        const evaluationId = operation.op === "create" ? undefined : operation.evaluation_id;
        const current = evaluationId ? currentById.get(evaluationId) : undefined;
        const fields = operation.op === "update"
          ? { ...current, ...operation.data }
          : operation.op === "create" ? operation.data : current ?? {};
        return (
          <div key={`${operation.op}-${evaluationId ?? index}`} className="submission-eval-op">
            <div className="submission-eval-op-header">
              <span
                className={cn(
                  "submission-pill status",
                  operation.op === "create" && "approved",
                  operation.op === "update" && "changed",
                  operation.op === "delete" && "rejected",
                )}
              >
                {operation.op}
              </span>
              {evaluationId && (
                <span className="submission-meta">Evaluation #{evaluationId}</span>
              )}
            </div>
            <EvaluationFields
              evaluation={fields}
              taskNames={taskNames}
              datasetNames={datasetNames}
            />
          </div>
        );
      })}
    </div>
  );
}

function EvaluationFields({
  evaluation,
  taskNames,
  datasetNames,
}: {
  evaluation: EvaluationSnapshot;
  taskNames: Map<number, string>;
  datasetNames: Map<number, string>;
}) {
  const { task_id: taskId, dataset_id: datasetId } = evaluation;
  const metrics = evaluation.metrics ?? {};

  return (
    <div className="submission-eval-fields">
      <Field label="Task" value={taskId ? taskNames.get(taskId) ?? `#${taskId}` : null} />
      <Field label="Dataset" value={datasetId ? datasetNames.get(datasetId) ?? `#${datasetId}` : null} />
      <Field label="Model" value={evaluation.model_name || null} />
      <Field label="Harness" value={evaluation.harness || null} />
      <Field label="Best rank" value={evaluation.best_rank ?? null} />
      <Field label="Parameters" value={evaluation.num_parameters ?? null} />
      <Field label="HF model URL" value={evaluation.hf_model_url || null} />
      <Field
        label="Open source"
        value={evaluation.is_open === undefined ? null : evaluation.is_open ? "Yes" : "No"}
      />
      <div className="submission-eval-metrics">
        <div className="submission-diff-label">Metrics</div>
        {Object.keys(metrics).length > 0 ? (
          <div className="submission-metric-list">
            {Object.entries(metrics).map(([name, value]) => (
              <span key={name} className="submission-metric-pill">
                {name}: {String(value)}
              </span>
            ))}
          </div>
        ) : (
          <EmptyInline>No metrics</EmptyInline>
        )}
      </div>
    </div>
  );
}

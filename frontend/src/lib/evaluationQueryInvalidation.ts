import type { Evaluation } from "@/lib/api/evaluations.types";
import type { QueryClient } from "@tanstack/react-query";
import type { Dataset, TaskPage, TrendingBenchmarksResponse } from "@/lib/api/catalog.types";
import { invalidatePaperDetails, invalidatePaperFeeds } from "@/lib/queryInvalidation";

type EvaluationContext = {
  id?: string | number;
  task_id?: string | number;
  dataset_id?: string | number;
};

export interface EvaluationChange {
  paperId: string;
  arxivId?: string;
  contexts: EvaluationContext[];
}

/** Capture both sides before a mutation: deleted/moved rows disappear after saving. */
export function evaluationChange(
  paperId: string,
  before: EvaluationContext[],
  operations: Array<
    | { kind: "create"; data: EvaluationContext }
    | { kind: "update"; evaluationId: number; data: EvaluationContext }
    | { kind: "delete"; evaluationId: number }
  >,
  arxivId?: string,
): EvaluationChange {
  const changedIds = new Set(operations.flatMap(operation =>
    operation.kind === "create" ? [] : [String(operation.evaluationId)],
  ));
  return {
    paperId,
    arxivId,
    contexts: [
      ...before.filter(row => row.id !== undefined && changedIds.has(String(row.id))),
      ...operations.flatMap(operation => operation.kind === "delete" ? [] : [operation.data]),
    ],
  };
}

/** Reconcile live catalog data only after the server has applied an evaluation change. */
export function refreshEvaluationQueries(queryClient: QueryClient, change: EvaluationChange) {
  const datasetIds = new Set(change.contexts.flatMap(row => row.dataset_id == null ? [] : [String(row.dataset_id)]));
  const taskIds = new Set(change.contexts.flatMap(row => row.task_id == null ? [] : [String(row.task_id)]));

  const affectedPaperIds = new Set([change.paperId]);
  const affectedPaperAliases = new Set<string>();
  if (change.arxivId) affectedPaperAliases.add(change.arxivId);
  const affectedLeaderboards = new Set(change.contexts.map(row => `${row.task_id}:${row.dataset_id}`));
  // Rank changes affect competing papers too. These two cache families contain
  // Evaluation[]; inspect their canonical IDs, never arbitrary catalog shapes.
  const evaluationQueries = queryClient.getQueryCache().findAll({ predicate: query =>
    query.queryKey[0] === "dataset-evals" ||
    (query.queryKey[0] === "evaluations" && query.queryKey[1] === "paper"),
  });
  for (const query of evaluationQueries) {
    for (const row of (query.state.data as Evaluation[] | undefined) ?? []) {
      if (!affectedLeaderboards.has(`${row.task_id}:${row.dataset_id}`)) continue;
      affectedPaperIds.add(String(row.paper_id));
      if (row.paper_arxiv_id) affectedPaperAliases.add(row.paper_arxiv_id);
    }
  }
  invalidatePaperDetails(queryClient, [...affectedPaperIds, ...affectedPaperAliases]);
  // Paper cards carry leaderboard rank badges. Stale them without fetching inactive feeds.
  invalidatePaperFeeds(queryClient);
  void queryClient.invalidateQueries({
    predicate: query => query.queryKey[0] === "evaluations" &&
      query.queryKey[1] === "paper" && affectedPaperIds.has(String(query.queryKey[2])),
  });

  void queryClient.invalidateQueries({ predicate: query => {
    const [family, identifier] = query.queryKey;
    switch (family) {
      case "dataset-evals":
      case "dataset-tasks":
        return datasetIds.has(String(identifier));
      case "dataset": {
        // Dataset readers use both numeric IDs and slugs; the response is canonical.
        const dataset = query.state.data as Dataset | undefined;
        return datasetIds.has(String(identifier)) || Boolean(dataset && datasetIds.has(String(dataset.id)));
      }
      case "task-page": {
        const page = query.state.data as TaskPage | undefined;
        return taskIds.has(String(identifier)) || Boolean(page && (
          taskIds.has(String(page.task.id)) ||
          page.subtask_benchmarks.some(group => taskIds.has(String(group.subtask_id))) ||
          page.benchmarks.some(dataset => datasetIds.has(String(dataset.id))) ||
          page.subtask_benchmarks.some(group => group.benchmarks.some(dataset => datasetIds.has(String(dataset.id))))
        ));
      }
      case "task-benchmark-trends": {
        const trends = query.state.data as TrendingBenchmarksResponse | undefined;
        return taskIds.has(String(identifier)) || Boolean(trends && taskIds.has(String(trends.task_id)));
      }
      default:
        return false;
    }
  } });
}

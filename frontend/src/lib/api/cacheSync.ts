import type { Query, QueryClient, QueryKey } from "@tanstack/react-query";

import type { Dataset, TaskPage, TrendingBenchmarksResponse } from "@/lib/api/catalog.types";
import type { Evaluation } from "@/lib/api/evaluations.types";
import type { Paper } from "@/lib/api/papers.types";
import { PAPER_LIST_FAMILIES, paperQueries } from "@/lib/api/queries";
import type { PendingEvaluationOperation } from "@/lib/pendingEdits";

/**
 * Reconcile React Query caches after the server applied a paper or evaluation
 * change. Keys follow `queries.ts`: `key[0]` is the family, `key[1]` the entity.
 */

const PAPER_EVALS = ["paper-evals"] as const;
const DATASET_EVALS = ["dataset-evals"] as const;

/** The entity a cache entry is about. */
const entityOf = (query: Query) => String(query.queryKey[1]);

function presentIds(identifiers: Array<string | null | undefined>): Set<string> {
  return new Set(identifiers.filter((id): id is string => Boolean(id)));
}

/** Every cache entry holding one paper, under each of its route IDs. */
function paperKeys(identifiers: Array<string | null | undefined>): QueryKey[] {
  return [...presentIds(identifiers)].flatMap((id) => [paperQueries.detail(id).queryKey, paperQueries.summary(id).queryKey]);
}

/** Approval responses contain no Paper; refetch mounted details and stale the rest. */
export function invalidatePaperDetails(queryClient: QueryClient, identifiers: Array<string | null | undefined>) {
  for (const queryKey of paperKeys(identifiers)) {
    void queryClient.invalidateQueries({ queryKey, exact: true });
  }
}

export function invalidatePaperFeeds(queryClient: QueryClient) {
  // Membership and ordering may change even in lists not containing this paper.
  // Fetch these stale families when readers return, not during the mutation.
  for (const family of PAPER_LIST_FAMILIES) {
    void queryClient.invalidateQueries({ queryKey: [family], refetchType: "none" });
  }
}

/**
 * Optimistically patch every cached copy of a paper. Returns the rollback.
 */
export async function patchPaperCaches(
  queryClient: QueryClient,
  identifiers: Array<string | null | undefined>,
  patch: (paper: Paper) => Paper,
): Promise<() => void> {
  const keys = paperKeys(identifiers);
  await Promise.all(keys.map((queryKey) => queryClient.cancelQueries({ queryKey, exact: true })));
  const snapshots = keys.map((queryKey) => ({ queryKey, data: queryClient.getQueryData<Paper>(queryKey) }));
  for (const { queryKey, data } of snapshots) {
    if (data) queryClient.setQueryData<Paper>(queryKey, patch(data));
  }
  return () => snapshots.forEach(({ queryKey, data }) => queryClient.setQueryData(queryKey, data));
}

type EvaluationCacheData = Evaluation[] | undefined;

function retitleEvaluations(rows: EvaluationCacheData, paperId: string, title: string): EvaluationCacheData {
  if (!rows?.some((row) => row.paper_id === paperId && row.paper_title !== title)) return rows;
  return rows.map((row) => (row.paper_id === paperId ? { ...row, paper_title: title } : row));
}

/**
 * Write the server's paper into its caches after an edit.
 *
 * The detail entry is replaced rather than invalidated: a refetch would
 * round-trip again and delay the visible change. Paper lists are marked stale
 * without refetching, and cached evaluation rows get the new paper title in
 * place so mounted leaderboards update without a request.
 */
export function refreshPaperQueries(queryClient: QueryClient, updatedPaper: Paper, identifiers: Array<string | undefined>) {
  const ids = presentIds([...identifiers, updatedPaper.id, updatedPaper.arxiv_id]);
  for (const id of ids) {
    queryClient.setQueryData(paperQueries.detail(id).queryKey, updatedPaper);
    // Update existing summaries without creating unused cache entries.
    queryClient.setQueriesData({ queryKey: paperQueries.summary(id).queryKey, exact: true }, updatedPaper);
  }

  invalidatePaperFeeds(queryClient);

  const paperId = String(updatedPaper.id);
  for (const queryKey of [PAPER_EVALS, DATASET_EVALS]) {
    queryClient.setQueriesData<EvaluationCacheData>({ queryKey }, (rows) => retitleEvaluations(rows, paperId, updatedPaper.title));
    void queryClient.invalidateQueries({ queryKey, refetchType: "none" });
  }
}

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
  operations: PendingEvaluationOperation[],
  arxivId?: string,
): EvaluationChange {
  const changedIds = new Set(operations.flatMap(operation =>
    operation.op === "create" ? [] : [String(operation.evaluation_id)],
  ));
  return {
    paperId,
    arxivId,
    contexts: [
      ...before.filter(row => row.id !== undefined && changedIds.has(String(row.id))),
      ...operations.flatMap(operation => operation.op === "delete" ? [] : [operation.data]),
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
  // Rank changes affect competing papers too. Both evaluation families hold Evaluation[].
  for (const queryKey of [DATASET_EVALS, PAPER_EVALS]) {
    for (const [, rows] of queryClient.getQueriesData<EvaluationCacheData>({ queryKey })) {
      for (const row of rows ?? []) {
        if (!affectedLeaderboards.has(`${row.task_id}:${row.dataset_id}`)) continue;
        affectedPaperIds.add(String(row.paper_id));
        if (row.paper_arxiv_id) affectedPaperAliases.add(row.paper_arxiv_id);
      }
    }
  }
  invalidatePaperDetails(queryClient, [...affectedPaperIds, ...affectedPaperAliases]);
  // Paper cards carry leaderboard rank badges. Stale them without fetching inactive feeds.
  invalidatePaperFeeds(queryClient);
  void queryClient.invalidateQueries({ queryKey: PAPER_EVALS, predicate: query => affectedPaperIds.has(entityOf(query)) });

  const identifiesDataset = (query: Query) => datasetIds.has(entityOf(query));
  void queryClient.invalidateQueries({ queryKey: DATASET_EVALS, predicate: identifiesDataset });
  void queryClient.invalidateQueries({ queryKey: ["dataset-tasks"], predicate: identifiesDataset });
  // Dataset readers use both numeric IDs and slugs; the response is canonical.
  void queryClient.invalidateQueries({ queryKey: ["dataset"], predicate: query => {
    const dataset = query.state.data as Dataset | undefined;
    return identifiesDataset(query) || Boolean(dataset && datasetIds.has(String(dataset.id)));
  } });
  void queryClient.invalidateQueries({ queryKey: ["task-page"], predicate: query => {
    const page = query.state.data as TaskPage | undefined;
    return taskIds.has(entityOf(query)) || Boolean(page && (
      taskIds.has(String(page.task.id)) ||
      page.subtask_benchmarks.some(group => taskIds.has(String(group.subtask_id))) ||
      page.benchmarks.some(dataset => datasetIds.has(String(dataset.id))) ||
      page.subtask_benchmarks.some(group => group.benchmarks.some(dataset => datasetIds.has(String(dataset.id))))
    ));
  } });
  void queryClient.invalidateQueries({ queryKey: ["task-benchmark-trends"], predicate: query => {
    const trends = query.state.data as TrendingBenchmarksResponse | undefined;
    return taskIds.has(entityOf(query)) || Boolean(trends && taskIds.has(String(trends.task_id)));
  } });
}

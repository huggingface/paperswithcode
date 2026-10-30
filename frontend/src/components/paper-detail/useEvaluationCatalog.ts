import { useMemo } from "react";
import { useQueries, useQueryClient } from "@tanstack/react-query";

import type { SearchableSelectOption } from "@/components/ui/searchable-select";
import { catalogApi } from "@/lib/api/catalog";
import type { Dataset, Task } from "@/lib/api/catalog.types";
import type { Evaluation, LeaderboardMetric } from "@/lib/api/evaluations.types";
import type { EditableEvaluationRow } from "@/lib/evaluationOperations";

const SEARCH_PAGE_SIZE = 100;

const taskKey = (id: string) => ["eval-edit", "task", id] as const;
const datasetKey = (id: string) => ["eval-edit", "dataset", id] as const;

function byId<T extends { id: string }>(...lists: Array<Array<T | undefined>>): Map<string, T> {
  return new Map(lists.flat().flatMap((item) => (item ? [[item.id, item] as const] : [])));
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

export interface LeaderboardMetrics {
  metrics: LeaderboardMetric[];
  loading: boolean;
  error: Error | null;
}

/**
 * Catalog lookups for the evaluation editor: names for the selected tasks and
 * datasets, which datasets support a harness, and each leaderboard's metrics.
 */
export function useEvaluationCatalog(rows: EditableEvaluationRow[], initialEvaluations: Evaluation[]) {
  const queryClient = useQueryClient();
  const taskIds = useMemo(() => unique(rows.map((row) => row.task_id)), [rows]);
  const datasetIds = useMemo(() => unique(rows.map((row) => row.dataset_id)), [rows]);
  const leaderboards = useMemo(
    () => unique(rows.map((row) => (row.task_id && row.dataset_id ? `${row.task_id}:${row.dataset_id}` : ""))),
    [rows],
  );

  // Stored rows name their task and dataset; anything picked since was seeded by its search.
  const storedTasks = useMemo(() => byId(initialEvaluations.map((evaluation): Task | undefined =>
    evaluation.task_name
      ? { id: evaluation.task_id, name: evaluation.task_name, slug: evaluation.task_slug, level: 0 }
      : undefined,
  )), [initialEvaluations]);
  const storedDatasets = useMemo(() => byId(initialEvaluations.map((evaluation): Dataset | undefined =>
    evaluation.dataset_name
      ? { id: evaluation.dataset_id, name: evaluation.dataset_name, slug: evaluation.dataset_slug }
      : undefined,
  )), [initialEvaluations]);

  const pickedTasks = useQueries({
    queries: taskIds.filter((id) => !storedTasks.has(id)).map((id) => ({
      queryKey: taskKey(id),
      queryFn: () => catalogApi.getTask(id),
      staleTime: Infinity,
    })),
    combine: (results) => results.map((result) => result.data),
  });
  // Task dataset lists say which stored datasets support a harness.
  const taskDatasets = useQueries({
    queries: taskIds.map((taskId) => ({
      queryKey: ["eval-edit", "task-datasets", taskId],
      queryFn: async () =>
        (await catalogApi.listDatasets({ task_id: Number(taskId), page_size: SEARCH_PAGE_SIZE })).results,
    })),
  });
  const listedDatasets = byId(...taskDatasets.map((result) => result.data ?? []));
  const pickedDatasets = useQueries({
    queries: datasetIds
      .filter((id) => !storedDatasets.has(id) && !listedDatasets.has(id))
      .map((id) => ({
        queryKey: datasetKey(id),
        queryFn: () => catalogApi.getDataset(id),
        staleTime: Infinity,
      })),
    combine: (results) => ({
      data: results.map((result) => result.data),
      loaded: results.every((result) => result.isSuccess),
    }),
  });
  const metricQueries = useQueries({
    queries: leaderboards.map((leaderboard) => {
      const [taskId, datasetId] = leaderboard.split(":");
      return {
        queryKey: ["eval-edit", "leaderboard-metrics", taskId, datasetId],
        queryFn: () => catalogApi.leaderboardMetrics(datasetId, taskId),
      };
    }),
  });

  const tasks = byId([...storedTasks.values()], pickedTasks);
  const datasets = byId([...storedDatasets.values()], [...listedDatasets.values()], pickedDatasets.data);
  const datasetListError = taskDatasets.find((result) => result.error)?.error ?? null;
  // Stored rows don't say whether their dataset supports a harness; until the
  // task lists load, saving would clear an existing harness.
  const harnessSupportKnown = taskDatasets.every((result) => result.isSuccess) && pickedDatasets.loaded;

  return {
    task: (id: string) => tasks.get(id),
    dataset: (id: string) => datasets.get(id),
    supportsHarness: (taskId: string, datasetId: string) =>
      Boolean(taskId && datasetId && datasets.get(datasetId)?.supports_harness),
    metrics: (taskId: string, datasetId: string): LeaderboardMetrics => {
      const query = metricQueries[leaderboards.indexOf(`${taskId}:${datasetId}`)];
      return { metrics: query?.data ?? [], loading: query?.isFetching ?? false, error: query?.error ?? null };
    },
    datasetListError,
    harnessSupportKnown,
    searchTasks: async (query: string): Promise<SearchableSelectOption[]> => {
      const response = await catalogApi.listTasks({
        page_size: SEARCH_PAGE_SIZE,
        ...(query ? { q: query } : {}),
      });
      response.results.forEach((task) => queryClient.setQueryData(taskKey(task.id), task));
      return response.results.map((task) => ({
        value: task.id,
        label: task.name,
        description: task.description?.slice(0, 100),
      }));
    },
    searchDatasets: (taskId: string) => async (query: string): Promise<SearchableSelectOption[]> => {
      const response = await catalogApi.listDatasets({
        task_id: Number(taskId),
        page_size: SEARCH_PAGE_SIZE,
        ...(query ? { q: query } : {}),
      });
      response.results.forEach((dataset) => queryClient.setQueryData(datasetKey(dataset.id), dataset));
      return response.results.map((dataset) => ({
        value: dataset.id,
        label: dataset.name,
        description: dataset.full_name,
      }));
    },
  };
}

export type EvaluationCatalog = ReturnType<typeof useEvaluationCatalog>;

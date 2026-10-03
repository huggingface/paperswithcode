import { getApiErrorMessage } from "@/lib/apiTransport";
import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Check, Plus, Trash2, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SearchableSelect, type SearchableSelectOption } from "@/components/ui/searchable-select";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  type Task as APITask,
  type Dataset,
} from "@/lib/api/catalog.types";
import {
  type Evaluation as APIEvaluation,
  type LeaderboardMetric,
} from "@/lib/api/evaluations.types";
import { catalogApi } from "@/lib/api/catalog";
import { evaluationsApi } from "@/lib/api/evaluations";
import { submissionsApi } from "@/lib/api/submissions";
import {
  mapApiEvaluationsToEditable,
  normalizeEvaluationOperations,
  toDirectEvaluationOperations,
  toPendingEvaluationOperations,
  type EditableEvaluationRow,
} from "@/lib/evaluationOperations";
import { useToast } from "@/hooks/use-toast";
import { PendingEditNotice } from "@/components/paper-detail/PendingEditNotice";
import { SuggestTaxonomyDialog } from "@/components/paper-detail/SuggestTaxonomyDialog";

const SEARCH_PAGE_SIZE = 100;

interface EditEvaluationsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId: string;
  arxivId?: string;
  initialEvaluations: APIEvaluation[];
  /** Paper task tags. Used to decide whether the Harness column is shown. */
  paperTasks?: Array<Pick<APITask, "id" | "name" | "slug">>;
  onSuccess?: () => void;
  /** `direct` applies immediately (admin path). `pending` submits an edit for
   *  admin review without touching live data. */
  submitMode?: "direct" | "pending";
  isAdmin?: boolean;
  /** When `submitMode === "pending"` and the signed-in user is a linked
   *  author of the paper, the notice copy acknowledges that. */
  isAuthor?: boolean;
}

function paperHasCodingAgentsTask(
  paperTasks: Array<Pick<APITask, "id" | "name" | "slug">> | undefined,
): boolean {
  return (paperTasks ?? []).some(
    (task) =>
      task.slug === "coding-agents" ||
      task.name.trim().toLowerCase() === "coding agents",
  );
}

function buildKnownTasksFromEvaluations(evaluations: APIEvaluation[]): Map<string, APITask> {
  const map = new Map<string, APITask>();
  evaluations.forEach((evaluation) => {
    if (evaluation.task_id && evaluation.task_name) {
      map.set(evaluation.task_id, {
        id: evaluation.task_id,
        name: evaluation.task_name,
        slug: evaluation.task_slug,
        level: 0,
      });
    }
  });
  return map;
}

function buildKnownDatasetsFromEvaluations(evaluations: APIEvaluation[]): Map<string, Dataset> {
  const map = new Map<string, Dataset>();
  evaluations.forEach((evaluation) => {
    if (evaluation.dataset_id && evaluation.dataset_name) {
      map.set(evaluation.dataset_id, {
        id: evaluation.dataset_id,
        name: evaluation.dataset_name,
        slug: evaluation.dataset_slug,
      });
    }
  });
  return map;
}

function leaderboardKey(taskId: string, datasetId: string): string {
  return `${taskId}:${datasetId}`;
}

export function EditEvaluationsDialog({
  open,
  onOpenChange,
  paperId,
  arxivId,
  initialEvaluations,
  paperTasks,
  onSuccess,
  submitMode = "direct",
  isAdmin = false,
  isAuthor = false,
}: EditEvaluationsDialogProps) {
  const showHarnessColumn = paperHasCodingAgentsTask(paperTasks);
  const [editedEvaluations, setEditedEvaluations] = useState<EditableEvaluationRow[]>([]);
  const [suggestionKind, setSuggestionKind] = useState<"benchmark" | "metric" | null>(null);
  const [knownTasks, setKnownTasks] = useState<Map<string, APITask>>(new Map());
  const [knownDatasets, setKnownDatasets] = useState<Map<string, Dataset>>(new Map());
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const hasSeededRef = useRef(false);
  const hasUserEditedRef = useRef(false);

  useEffect(() => {
    if (!open) {
      hasSeededRef.current = false;
      hasUserEditedRef.current = false;
      return;
    }
    if (hasSeededRef.current) return;
    if (hasUserEditedRef.current) return;
    if (initialEvaluations.length === 0) return;
    hasSeededRef.current = true;
    setEditedEvaluations(mapApiEvaluationsToEditable(initialEvaluations));
    setKnownTasks(buildKnownTasksFromEvaluations(initialEvaluations));
    setKnownDatasets(buildKnownDatasetsFromEvaluations(initialEvaluations));
  }, [open, initialEvaluations]);

  const uniqueTaskIds = useMemo(() => {
    return Array.from(new Set(editedEvaluations.map(e => e.task_id).filter(id => id && id !== '')));
  }, [editedEvaluations]);

  const uniqueLeaderboards = useMemo(() => {
    const pairs = new Set<string>();
    editedEvaluations.forEach((evaluation) => {
      if (evaluation.task_id && evaluation.dataset_id) {
        pairs.add(leaderboardKey(evaluation.task_id, evaluation.dataset_id));
      }
    });
    return Array.from(pairs);
  }, [editedEvaluations]);

  const taskDatasetsQueries = useQuery({
    queryKey: ['datasets-by-tasks-for-eval-edit', uniqueTaskIds, open],
    queryFn: async () => {
      const datasetsMap: Record<string, Dataset[]> = {};

      await Promise.all(
        uniqueTaskIds.map(async (taskId) => {
          try {
            const response = await catalogApi.listDatasets({ task_id: parseInt(taskId), page_size: SEARCH_PAGE_SIZE });
            datasetsMap[taskId] = response.results;
          } catch (error) {
            console.error(`Error fetching datasets for task ${taskId}:`, error);
            datasetsMap[taskId] = [];
          }
        }),
      );

      return datasetsMap;
    },
    enabled: open && uniqueTaskIds.length > 0,
  });

  useEffect(() => {
    if (!taskDatasetsQueries.data) return;
    setKnownDatasets((prev) => {
      const next = new Map(prev);
      Object.values(taskDatasetsQueries.data).forEach((datasets) => {
        datasets.forEach((dataset) => {
          next.set(dataset.id, dataset);
        });
      });
      return next;
    });
  }, [taskDatasetsQueries.data]);

  const leaderboardMetricsQueries = useQuery({
    queryKey: ['leaderboard-metrics-for-eval-edit', uniqueLeaderboards, open],
    queryFn: async () => {
      const metricsMap: Record<string, LeaderboardMetric[]> = {};

      await Promise.all(
        uniqueLeaderboards.map(async (key) => {
          const [taskId, datasetId] = key.split(':');
          try {
            metricsMap[key] = await catalogApi.leaderboardMetrics(datasetId, taskId);
          } catch (error) {
            console.error(`Error fetching metrics for leaderboard ${key}:`, error);
            metricsMap[key] = [];
          }
        }),
      );

      return metricsMap;
    },
    enabled: open && uniqueLeaderboards.length > 0,
  });

  const searchTasks = async (query: string): Promise<SearchableSelectOption[]> => {
    const response = await catalogApi.listTasks({
      page_size: SEARCH_PAGE_SIZE,
      ...(query ? { q: query } : {}),
    });
    setKnownTasks((prev) => {
      const next = new Map(prev);
      response.results.forEach((task) => next.set(task.id, task));
      return next;
    });
    return response.results.map((task) => ({
      value: task.id,
      label: task.name,
      description: task.description?.slice(0, 100),
    }));
  };

  const searchDatasetsForTask = (taskId: string) => async (query: string): Promise<SearchableSelectOption[]> => {
    const response = await catalogApi.listDatasets({
      task_id: parseInt(taskId),
      page_size: SEARCH_PAGE_SIZE,
      ...(query ? { q: query } : {}),
    });
    setKnownDatasets((prev) => {
      const next = new Map(prev);
      response.results.forEach((dataset) => next.set(dataset.id, dataset));
      return next;
    });
    return response.results.map((dataset) => ({
      value: dataset.id,
      label: dataset.name,
      description: dataset.full_name,
    }));
  };

  const selectedDatasetSupportsHarness = (taskId: string, datasetId: string): boolean => {
    if (!taskId || !datasetId) return false;
    const dataset = knownDatasets.get(datasetId);
    return Boolean(dataset?.supports_harness);
  };

  const getMetricOptionsForLeaderboard = (
    taskId: string,
    datasetId: string,
    currentMetricName: string,
  ): SearchableSelectOption[] => {
    if (!taskId || !datasetId) return [];

    const configuredMetrics =
      leaderboardMetricsQueries.data?.[leaderboardKey(taskId, datasetId)] || [];
    const options: SearchableSelectOption[] = configuredMetrics.map((metric) => ({
      value: metric.metric_name,
      label: metric.metric_name,
      description:
        metric.metric_direction === 'higher_is_better'
          ? 'Higher is better'
          : 'Lower is better',
    }));

    if (
      currentMetricName &&
      !options.some((option) => option.value === currentMetricName)
    ) {
      options.unshift({
        value: currentMetricName,
        label: `${currentMetricName} (legacy)`,
      });
    }

    return options;
  };

  const saveEvaluationsMutation = useMutation({
    mutationFn: async ({ paperId, evaluations }: {
      paperId: string;
      evaluations: EditableEvaluationRow[];
    }): Promise<{ submitted: boolean }> => {
      const canonical = normalizeEvaluationOperations(
        evaluations,
        selectedDatasetSupportsHarness,
      );
      if (!isAdmin && submitMode === "direct" && canonical.length > 50) {
        throw new Error(
          "Contributor evaluation batches are limited to 50 operations; contact an admin.",
        );
      }
      if (canonical.length === 0) return { submitted: false };

      const numericPaperId = Number.parseInt(paperId, 10);
      if (submitMode === "pending") {
        await submissionsApi.submit({
          paper_id: numericPaperId,
          edit_type: "evaluations",
          proposed_payload: {
            operations: toPendingEvaluationOperations(canonical),
          },
        });
      } else {
        await evaluationsApi.batch(
          numericPaperId,
          toDirectEvaluationOperations(numericPaperId, canonical),
        );
      }
      return { submitted: true };
    },
    onSuccess: (result) => {
      if (submitMode === "pending") {
        if (result?.submitted) {
          toast({
            title: "Edit submitted for review",
            description:
              "Thanks! An admin will review your proposed evaluation changes shortly.",
          });
        } else {
          toast({
            title: "No changes to submit",
            description: "Your evaluation list matches the existing data.",
          });
        }
        onSuccess?.();
        onOpenChange(false);
        return;
      }
      queryClient.invalidateQueries({ queryKey: ['paper-arxiv', arxivId] });
      queryClient.invalidateQueries({ queryKey: ['evaluations', 'paper', paperId] });
      onSuccess?.();
      onOpenChange(false);
    },
    onError: (err: unknown) => {
      const description = getApiErrorMessage(
        err,
        submitMode === "pending"
          ? "Failed to submit your edit. Please try again."
          : "Failed to update evaluations.",
      );
      toast({
        title:
          submitMode === "pending"
            ? "Could not submit edit"
            : "Could not save evaluations",
        description,
        variant: "destructive",
      });
    },
  });

  const handleAddEvaluation = () => {
    hasUserEditedRef.current = true;
    setEditedEvaluations([
      ...editedEvaluations,
      {
        task_id: '',
        dataset_id: '',
        model_name: '',
        harness: '',
        metric_name: '',
        metric_value: '',
        original_metrics: {},
        original_metric_name: '',
        best_rank: '',
        num_parameters: '',
        hf_model_url: '',
        is_open: true,
        operation: 'create',
      },
    ]);
  };

  const handleDeleteEvaluation = (index: number) => {
    hasUserEditedRef.current = true;
    const evaluation = editedEvaluations[index];
    if (evaluation.id) {
      if (
        !window.confirm(
          "Delete this evaluation? You will be asked to sign in again if your session is older than 15 minutes.",
        )
      ) {
        return;
      }
      setEditedEvaluations(
        editedEvaluations.map((e, i) =>
          i === index ? { ...e, operation: 'delete' as const } : e
        )
      );
    } else {
      setEditedEvaluations(editedEvaluations.filter((_, i) => i !== index));
    }
  };

  const handleUpdateEvaluationField = (
    index: number,
    field: keyof EditableEvaluationRow,
    value: string
  ) => {
    hasUserEditedRef.current = true;
    setEditedEvaluations(
      editedEvaluations.map((e, i) => {
        if (i !== index || e[field] === value) return e;
        const updated = { ...e, [field]: value };

        if (field === 'task_id' || field === 'dataset_id') {
          // Scores belong to a leaderboard; moving the row requires fresh scores.
          updated.original_metrics = {};
          updated.original_metric_name = '';
          updated.metric_value = '';
          updated.best_rank = '';
        }

        if (field === 'task_id') {
          updated.dataset_id = '';
          updated.metric_name = '';
          updated.harness = '';
        }

        if (field === 'dataset_id') {
          updated.metric_name = '';
          if (value && !selectedDatasetSupportsHarness(updated.task_id, value)) {
            updated.harness = '';
          }
        }

        if (e.operation === 'unchanged') {
          updated.operation = 'update';
        }
        return updated;
      })
    );
  };

  const handleToggleEvaluationOpen = (index: number, isOpen: boolean) => {
    hasUserEditedRef.current = true;
    setEditedEvaluations(
      editedEvaluations.map((e, i) => {
        if (i !== index) return e;
        const updated = { ...e, is_open: isOpen };
        if (e.operation === 'unchanged') {
          updated.operation = 'update';
        }
        return updated;
      })
    );
  };

  const handleSave = () => {
    const evaluationsToSave = editedEvaluations.filter(
      e => e.operation !== 'delete' || e.id
    );
    saveEvaluationsMutation.mutate({
      paperId,
      evaluations: evaluationsToSave,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl max-h-[800px]">
        <DialogHeader>
          <DialogTitle>Edit Evaluation Results</DialogTitle>
          <DialogDescription>
            Add, edit, or remove evaluation results for this paper. Each row represents a benchmark result.
          </DialogDescription>
        </DialogHeader>
        {submitMode === "pending" && <PendingEditNotice isAuthor={isAuthor} />}

        <div className="py-4 overflow-y-auto max-h-[600px]">
          {editedEvaluations.filter(e => e.operation !== 'delete').length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-2 px-2 font-medium text-sm min-w-[180px]">Task</th>
                    <th className="text-left py-2 px-2 font-medium text-sm min-w-[180px]">Dataset</th>
                    <th
                      className={`text-left py-2 px-2 font-medium text-sm ${
                        showHarnessColumn ? "min-w-[140px]" : "min-w-[240px]"
                      }`}
                    >
                      Model
                    </th>
                    {showHarnessColumn && (
                      <th className="text-left py-2 px-2 font-medium text-sm min-w-[140px]">Harness</th>
                    )}
                    <th className="text-left py-2 px-2 font-medium text-sm min-w-[140px]">Metric</th>
                    <th className="text-left py-2 px-2 font-medium text-sm">Value</th>
                    <th className="text-left py-2 px-2 font-medium text-sm">Parameters</th>
                    <th className="text-left py-2 px-2 font-medium text-sm min-w-[200px]">HF model URL</th>
                    <th className="text-left py-2 px-2 font-medium text-sm w-20">Open source</th>
                    <th className="text-left py-2 px-2 font-medium text-sm w-16">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {editedEvaluations.map((evaluation, index) => {
                    if (evaluation.operation === 'delete') return null;

                    const selectedTask = knownTasks.get(evaluation.task_id);
                    const selectedDataset = knownDatasets.get(evaluation.dataset_id);
                    const metricOptions = getMetricOptionsForLeaderboard(
                      evaluation.task_id,
                      evaluation.dataset_id,
                      evaluation.metric_name,
                    );
                    const metricsLoading =
                      Boolean(evaluation.task_id && evaluation.dataset_id) &&
                      leaderboardMetricsQueries.isFetching;

                    return (
                      <tr key={index} className="border-b border-border">
                        <td className="py-2 px-2">
                          <SearchableSelect
                            value={evaluation.task_id}
                            onChange={(value) => handleUpdateEvaluationField(index, 'task_id', value)}
                            placeholder="Select task"
                            searchPlaceholder="Search tasks..."
                            emptyMessage="No tasks found."
                            selectedOption={
                              selectedTask
                                ? { value: selectedTask.id, label: selectedTask.name }
                                : null
                            }
                            queryKey={['eval-edit-task-search']}
                            queryFn={searchTasks}
                            enabled={open}
                          />
                        </td>
                        <td className="py-2 px-2">
                          <SearchableSelect
                            value={evaluation.dataset_id}
                            onChange={(value) => handleUpdateEvaluationField(index, 'dataset_id', value)}
                            placeholder={evaluation.task_id ? "Select dataset" : "Select task first"}
                            searchPlaceholder="Search datasets..."
                            emptyMessage={
                              evaluation.task_id
                                ? "No datasets found for this task."
                                : "Select a task first."
                            }
                            disabled={!evaluation.task_id}
                            selectedOption={
                              selectedDataset
                                ? { value: selectedDataset.id, label: selectedDataset.name }
                                : null
                            }
                            queryKey={['eval-edit-dataset-search', evaluation.task_id]}
                            queryFn={searchDatasetsForTask(evaluation.task_id)}
                            enabled={open && Boolean(evaluation.task_id)}
                          />
                        </td>
                        <td className="py-2 px-2">
                          <Input
                            type="text"
                            className="w-full text-sm"
                            placeholder="Model name"
                            value={evaluation.model_name}
                            onChange={(e) => handleUpdateEvaluationField(index, 'model_name', e.target.value)}
                          />
                        </td>
                        {showHarnessColumn && (
                          <td className="py-2 px-2">
                            {selectedDatasetSupportsHarness(evaluation.task_id, evaluation.dataset_id) ? (
                              <Input
                                type="text"
                                className="w-full text-sm"
                                placeholder="Claude Code, Terminus, ..."
                                value={evaluation.harness}
                                onChange={(e) => handleUpdateEvaluationField(index, 'harness', e.target.value)}
                              />
                            ) : (
                              <span className="text-xs text-muted-foreground">
                                Not supported
                              </span>
                            )}
                          </td>
                        )}
                        <td className="py-2 px-2">
                          {!evaluation.task_id || !evaluation.dataset_id ? (
                            <span className="text-xs text-muted-foreground">
                              Select task + dataset
                            </span>
                          ) : metricsLoading ? (
                            <span className="inline-flex items-center text-xs text-muted-foreground">
                              <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                              Loading metrics...
                            </span>
                          ) : metricOptions.length > 0 ? (
                            <select
                              className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
                              value={evaluation.metric_name}
                              onChange={(e) =>
                                handleUpdateEvaluationField(index, 'metric_name', e.target.value)
                              }
                            >
                              <option value="">Select metric</option>
                              {metricOptions.map((option) => (
                                <option key={option.value} value={option.value}>
                                  {option.label}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <span className="text-xs text-muted-foreground">
                              No configured metrics
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-2">
                          <Input
                            type="text"
                            className="w-full text-sm"
                            placeholder="44.9"
                            value={evaluation.metric_value}
                            onChange={(e) => handleUpdateEvaluationField(index, 'metric_value', e.target.value)}
                          />
                        </td>
                        <td className="py-2 px-2">
                          <Input
                            type="number"
                            min={0}
                            step={1}
                            className="w-full text-sm"
                            placeholder="e.g. 7000000000"
                            value={evaluation.num_parameters}
                            onChange={(e) => handleUpdateEvaluationField(index, 'num_parameters', e.target.value)}
                            title="Raw model parameter count (e.g. 7000000000 for a 7B model). Leave blank if unknown."
                          />
                        </td>
                        <td className="py-2 px-2">
                          <Input
                            type="url"
                            className="w-full text-sm"
                            placeholder="https://huggingface.co/org/model"
                            value={evaluation.hf_model_url}
                            onChange={(e) => handleUpdateEvaluationField(index, 'hf_model_url', e.target.value)}
                            title="Hugging Face model page for this row (must start with https://huggingface.co/). Leave blank if none."
                          />
                        </td>
                        <td className="py-2 px-2 text-center">
                          <input
                            type="checkbox"
                            className="h-4 w-4 align-middle"
                            checked={evaluation.is_open}
                            onChange={(e) => handleToggleEvaluationOpen(index, e.target.checked)}
                            title="Whether the evaluated model is open-source. Uncheck for closed-source models."
                          />
                        </td>
                        <td className="py-2 px-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteEvaluation(index)}
                            className="h-8 w-8 p-0 text-destructive hover:text-destructive"
                            title={evaluation.id && !isAdmin ? "Only administrators can delete published results" : "Remove row"}
                            disabled={Boolean(evaluation.id) && !isAdmin}
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Database className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p>No evaluation results yet</p>
              <p className="text-sm mt-2">Click "Add Row" below to add a new evaluation</p>
            </div>
          )}

          <div className="mt-4">
            <Button
              variant="outline"
              size="sm"
              onClick={handleAddEvaluation}
              className="flex items-center space-x-2"
            >
              <Plus className="w-4 h-4" />
              <span>Add Row</span>
            </Button>
          </div>
        </div>

        <DialogFooter>
          <div className="flex flex-wrap gap-2 sm:mr-auto">
            <Button variant="ghost" onClick={() => setSuggestionKind("benchmark")}>
              Suggest a new benchmark
            </Button>
            <Button variant="ghost" onClick={() => setSuggestionKind("metric")}>
              Suggest a new metric
            </Button>
          </div>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={saveEvaluationsMutation.isPending}
          >
            {saveEvaluationsMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                {submitMode === "pending" ? "Submitting..." : "Saving..."}
              </>
            ) : (
              <>
                <Check className="w-4 h-4 mr-2" />
                {submitMode === "pending" ? "Submit for review" : "Save Changes"}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
      <SuggestTaxonomyDialog
        open={suggestionKind !== null}
        onOpenChange={(isOpen) => {
          if (!isOpen) setSuggestionKind(null);
        }}
        paperId={paperId}
        kind={suggestionKind ?? "benchmark"}
      />
    </Dialog>
  );
}

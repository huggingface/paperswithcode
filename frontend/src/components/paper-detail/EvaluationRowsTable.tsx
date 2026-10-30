import { Loader2, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SearchableSelect, type SearchableSelectOption } from "@/components/ui/searchable-select";
import type { EditableEvaluationRow, EvaluationDraftError } from "@/lib/evaluationOperations";
import type { EvaluationCatalog } from "./useEvaluationCatalog";

export type EditableField = "task_id" | "dataset_id" | "model_name" | "harness" | "metric_name"
  | "metric_value" | "num_parameters" | "hf_model_url";

interface EvaluationRowsTableProps {
  rows: EditableEvaluationRow[];
  catalog: EvaluationCatalog;
  draftErrors: EvaluationDraftError[];
  errorId: string;
  isAdmin: boolean;
  showHarnessColumn: boolean;
  onFieldChange: (index: number, field: EditableField, value: string) => void;
  onOpenSourceChange: (index: number, isOpen: boolean) => void;
  onDelete: (index: number) => void;
}

function metricOptions(
  catalog: EvaluationCatalog,
  row: EditableEvaluationRow,
): SearchableSelectOption[] {
  const options: SearchableSelectOption[] = catalog.metrics(row.task_id, row.dataset_id).metrics.map((metric) => ({
    value: metric.metric_name,
    label: metric.metric_name,
    description: metric.metric_direction === "higher_is_better" ? "Higher is better" : "Lower is better",
  }));
  if (row.metric_name && !options.some((option) => option.value === row.metric_name)) {
    options.unshift({ value: row.metric_name, label: `${row.metric_name} (legacy)` });
  }
  return options;
}

const th = "text-left py-2 px-2 font-medium text-sm";

/** One editable row per evaluation; deleted rows stay in `rows` but are hidden. */
export function EvaluationRowsTable({
  rows,
  catalog,
  draftErrors,
  errorId,
  isAdmin,
  showHarnessColumn,
  onFieldChange,
  onOpenSourceChange,
  onDelete,
}: EvaluationRowsTableProps) {
  const hasError = (rowIndex: number, field: EvaluationDraftError["field"]) =>
    draftErrors.some((error) => error.rowIndex === rowIndex && error.field === field);
  const fieldError = (rowIndex: number, field: EvaluationDraftError["field"]) => {
    const error = draftErrors.find((candidate) => candidate.rowIndex === rowIndex && candidate.field === field);
    return error ? (
      <p id={`${errorId}-${rowIndex}-${field}-error`} className="text-xs text-destructive">
        {error.message}
      </p>
    ) : null;
  };
  const describedInput = (rowIndex: number, field: EvaluationDraftError["field"]) => ({
    id: `${errorId}-${rowIndex}-${field}`,
    "aria-invalid": hasError(rowIndex, field),
    "aria-describedby": `${errorId}-${rowIndex}-${field}-error`,
  });

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-border">
            <th className={`${th} min-w-[180px]`}>Task</th>
            <th className={`${th} min-w-[180px]`}>Dataset</th>
            <th className={`${th} ${showHarnessColumn ? "min-w-[140px]" : "min-w-[240px]"}`}>Model</th>
            {showHarnessColumn && <th className={`${th} min-w-[140px]`}>Harness</th>}
            <th className={`${th} min-w-[140px]`}>Metric</th>
            <th className={th}>Value</th>
            <th className={th}>Parameters</th>
            <th className={`${th} min-w-[200px]`}>HF model URL</th>
            <th className={`${th} w-20`}>Open source</th>
            <th className={`${th} w-16`}>Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            if (row.operation === "delete") return null;
            const task = catalog.task(row.task_id);
            const dataset = catalog.dataset(row.dataset_id);
            const leaderboard = catalog.metrics(row.task_id, row.dataset_id);
            const options = metricOptions(catalog, row);

            return (
              <tr key={index} className="border-b border-border">
                <td className="py-2 px-2">
                  <div role="group" aria-label="Task" aria-describedby={`${errorId}-${index}-task_id-error`}>
                    <SearchableSelect
                      value={row.task_id}
                      onChange={(value) => onFieldChange(index, "task_id", value)}
                      placeholder="Select task"
                      searchPlaceholder="Search tasks..."
                      emptyMessage="No tasks found."
                      selectedOption={task ? { value: task.id, label: task.name } : null}
                      queryKey={["eval-edit-task-search"]}
                      queryFn={catalog.searchTasks}
                    />
                    {fieldError(index, "task_id")}
                  </div>
                </td>
                <td className="py-2 px-2">
                  <div role="group" aria-label="Dataset" aria-describedby={`${errorId}-${index}-dataset_id-error`}>
                    <SearchableSelect
                      value={row.dataset_id}
                      onChange={(value) => onFieldChange(index, "dataset_id", value)}
                      placeholder={row.task_id ? "Select dataset" : "Select task first"}
                      searchPlaceholder="Search datasets..."
                      emptyMessage={row.task_id ? "No datasets found for this task." : "Select a task first."}
                      disabled={!row.task_id}
                      selectedOption={dataset ? { value: dataset.id, label: dataset.name } : null}
                      queryKey={["eval-edit-dataset-search", row.task_id]}
                      queryFn={catalog.searchDatasets(row.task_id)}
                      enabled={Boolean(row.task_id)}
                    />
                    {fieldError(index, "dataset_id")}
                  </div>
                </td>
                <td className="py-2 px-2">
                  <Input
                    type="text"
                    className="w-full text-sm"
                    placeholder="Model name"
                    value={row.model_name}
                    onChange={(e) => onFieldChange(index, "model_name", e.target.value)}
                  />
                </td>
                {showHarnessColumn && (
                  <td className="py-2 px-2">
                    {catalog.supportsHarness(row.task_id, row.dataset_id) ? (
                      <Input
                        type="text"
                        className="w-full text-sm"
                        placeholder="Claude Code, Terminus, ..."
                        value={row.harness}
                        onChange={(e) => onFieldChange(index, "harness", e.target.value)}
                      />
                    ) : (
                      <span className="text-xs text-muted-foreground">Not supported</span>
                    )}
                  </td>
                )}
                <td className="py-2 px-2">
                  {!row.task_id || !row.dataset_id ? (
                    <span className="text-xs text-muted-foreground">Select task + dataset</span>
                  ) : leaderboard.loading ? (
                    <span className="inline-flex items-center text-xs text-muted-foreground">
                      <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                      Loading metrics...
                    </span>
                  ) : options.length > 0 ? (
                    <select
                      className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
                      {...describedInput(index, "metric_name")}
                      value={row.metric_name}
                      onChange={(e) => onFieldChange(index, "metric_name", e.target.value)}
                    >
                      <option value="">Select metric</option>
                      {options.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  ) : !leaderboard.error && (
                    <span className="text-xs text-muted-foreground">No configured metrics</span>
                  )}
                  {leaderboard.error && (
                    <p className="text-xs text-destructive">Could not load metrics</p>
                  )}
                  {fieldError(index, "metric_name")}
                </td>
                <td className="py-2 px-2">
                  <Input
                    type="text"
                    className="w-full text-sm"
                    placeholder="44.9"
                    {...describedInput(index, "metric_value")}
                    value={row.metric_value}
                    onChange={(e) => onFieldChange(index, "metric_value", e.target.value)}
                  />
                  {fieldError(index, "metric_value")}
                </td>
                <td className="py-2 px-2">
                  <Input
                    type="number"
                    min={0}
                    step={1}
                    className="w-full text-sm"
                    placeholder="e.g. 7000000000"
                    {...describedInput(index, "num_parameters")}
                    value={row.num_parameters}
                    onChange={(e) => onFieldChange(index, "num_parameters", e.target.value)}
                    title="Raw model parameter count (e.g. 7000000000 for a 7B model). Leave blank if unknown."
                  />
                  {fieldError(index, "num_parameters")}
                </td>
                <td className="py-2 px-2">
                  <Input
                    type="url"
                    className="w-full text-sm"
                    placeholder="https://huggingface.co/org/model"
                    value={row.hf_model_url}
                    onChange={(e) => onFieldChange(index, "hf_model_url", e.target.value)}
                    title="Hugging Face model page for this row (must start with https://huggingface.co/). Leave blank if none."
                  />
                </td>
                <td className="py-2 px-2 text-center">
                  <input
                    type="checkbox"
                    className="h-4 w-4 align-middle"
                    checked={row.is_open}
                    onChange={(e) => onOpenSourceChange(index, e.target.checked)}
                    title="Whether the evaluated model is open-source. Uncheck for closed-source models."
                  />
                </td>
                <td className="py-2 px-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onDelete(index)}
                    className="h-8 w-8 p-0 text-destructive hover:text-destructive"
                    title={row.id && !isAdmin ? "Only administrators can delete published results" : "Remove row"}
                    disabled={Boolean(row.id) && !isAdmin}
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
  );
}

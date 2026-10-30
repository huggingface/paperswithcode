import { useId, useMemo, useState } from "react";
import { Plus, Database } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import type { Task } from "@/lib/api/catalog.types";
import type { Evaluation } from "@/lib/api/evaluations.types";
import { evaluationsApi } from "@/lib/api/evaluations";
import {
  mapApiEvaluationsToEditable,
  prepareEvaluationDraft,
  validateEvaluationDraft,
  toDirectEvaluationOperations,
  type EditableEvaluationRow,
} from "@/lib/evaluationOperations";
import { evaluationChange, refreshEvaluationQueries } from "@/lib/evaluationQueryInvalidation";
import type { PendingEvaluationOperation } from "@/lib/pendingEdits";
import { useToast } from "@/hooks/use-toast";
import { EvaluationRowsTable, type EditableField } from "./EvaluationRowsTable";
import { PaperEditDialogShell } from "./PaperEditDialogShell";
import { SuggestTaxonomyDialog } from "./SuggestTaxonomyDialog";
import { useEvaluationCatalog } from "./useEvaluationCatalog";
import { usePaperSectionEdit, type PaperSectionEditorProps } from "./usePaperSectionEdit";

interface EditEvaluationsDialogProps extends PaperSectionEditorProps {
  initialEvaluations: Evaluation[];
  /** Paper task tags. Used to decide whether the Harness column is shown. */
  paperTasks?: Array<Pick<Task, "id" | "name" | "slug">>;
  isAdmin?: boolean;
}

const NEW_ROW: EditableEvaluationRow = {
  task_id: "",
  dataset_id: "",
  model_name: "",
  harness: "",
  metric_name: "",
  metric_value: "",
  original_metrics: {},
  original_metric_name: "",
  best_rank: "",
  num_parameters: "",
  hf_model_url: "",
  is_open: true,
  operation: "create",
};

function paperHasCodingAgentsTask(paperTasks: EditEvaluationsDialogProps["paperTasks"]): boolean {
  return (paperTasks ?? []).some(
    (task) => task.slug === "coding-agents" || task.name.trim().toLowerCase() === "coding agents",
  );
}

/** Marks an untouched stored row as edited. */
function touched(row: EditableEvaluationRow, changes: Partial<EditableEvaluationRow>): EditableEvaluationRow {
  return { ...row, ...changes, operation: row.operation === "unchanged" ? "update" : row.operation };
}

export function EditEvaluationsDialog({
  onOpenChange,
  paperId,
  arxivId,
  initialEvaluations,
  paperTasks,
  submitMode = "direct",
  isAdmin = false,
  isAuthor = false,
}: EditEvaluationsDialogProps) {
  const errorId = useId();
  const showHarnessColumn = paperHasCodingAgentsTask(paperTasks);
  // Until the first edit the rows follow `initialEvaluations`, which may still be loading.
  const [draft, setDraft] = useState<EditableEvaluationRow[] | null>(null);
  const initialRows = useMemo(() => mapApiEvaluationsToEditable(initialEvaluations), [initialEvaluations]);
  const rows = draft ?? initialRows;
  const [hasAttemptedSave, setHasAttemptedSave] = useState(false);
  const draftErrors = hasAttemptedSave ? validateEvaluationDraft(rows) : [];
  const [suggestionKind, setSuggestionKind] = useState<"benchmark" | "metric" | null>(null);
  const catalog = useEvaluationCatalog(rows, initialEvaluations);
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const save = usePaperSectionEdit({
    editType: "evaluations",
    paperId,
    arxivId,
    submitMode,
    messages: {
      proposal: "evaluation changes",
      noun: "evaluations",
      failure: "Failed to update evaluations.",
    },
    toPendingPayload: (operations: PendingEvaluationOperation[]) => ({ operations }),
    applyDirect: async (operations) => {
      if (!isAdmin && operations.length > 50) {
        throw new Error("Contributor evaluation batches are limited to 50 operations; contact an admin.");
      }
      const numericPaperId = Number(paperId);
      await evaluationsApi.batch(numericPaperId, toDirectEvaluationOperations(numericPaperId, operations));
    },
    onSaved: (operations, { live }) => {
      if (live) {
        refreshEvaluationQueries(
          queryClient,
          evaluationChange(paperId, initialEvaluations, operations, arxivId),
        );
      }
    },
    onClose: () => onOpenChange(false),
  });

  const updateRow = (index: number, update: (row: EditableEvaluationRow) => EditableEvaluationRow) =>
    setDraft(rows.map((row, i) => (i === index ? update(row) : row)));

  const handleDelete = (index: number) => {
    if (!rows[index].id) {
      setDraft(rows.filter((_, i) => i !== index));
      return;
    }
    if (
      !window.confirm(
        "Delete this evaluation? You will be asked to sign in again if your session is older than 15 minutes.",
      )
    ) return;
    updateRow(index, (row) => ({ ...row, operation: "delete" }));
  };

  const handleFieldChange = (index: number, field: EditableField, value: string) => {
    updateRow(index, (row) => {
      if (row[field] === value) return row;
      const changes: Partial<EditableEvaluationRow> = { [field]: value };
      if (field === "task_id" || field === "dataset_id") {
        // Scores belong to a leaderboard; moving the row requires fresh scores.
        Object.assign(changes, { original_metrics: {}, original_metric_name: "", metric_value: "", best_rank: "", metric_name: "" });
      }
      if (field === "task_id") Object.assign(changes, { dataset_id: "", harness: "" });
      if (field === "dataset_id" && value && !catalog.supportsHarness(row.task_id, value)) {
        changes.harness = "";
      }
      return touched(row, changes);
    });
  };

  const handleSave = () => {
    setHasAttemptedSave(true);
    const prepared = prepareEvaluationDraft(rows, catalog.supportsHarness);
    if (!prepared.valid) return;
    if (prepared.operations.length === 0) {
      toast({ title: "No changes to submit", description: "Your evaluation list matches the existing data." });
      return;
    }
    save.mutate(prepared.operations);
  };

  const visibleRowNumber = (rowIndex: number) =>
    rows.slice(0, rowIndex + 1).filter((row) => row.operation !== "delete").length;

  return (
    <>
      <PaperEditDialogShell
        title="Edit Evaluation Results"
        description="Add, edit, or remove evaluation results for this paper. Each row represents a benchmark result."
        className="max-w-6xl max-h-[800px]"
        submitMode={submitMode}
        isAuthor={isAuthor}
        onOpenChange={onOpenChange}
        onSave={handleSave}
        isSaving={save.isPending}
        saveDisabled={!catalog.harnessSupportKnown}
        footerStart={
          <div className="flex flex-wrap gap-2 sm:mr-auto">
            <Button variant="ghost" onClick={() => setSuggestionKind("benchmark")}>
              Suggest a new benchmark
            </Button>
            <Button variant="ghost" onClick={() => setSuggestionKind("metric")}>
              Suggest a new metric
            </Button>
          </div>
        }
      >
        {draftErrors.length > 0 && (
          <div role="alert" className="text-sm text-destructive">
            Fix the following errors before saving. No changes have been submitted.
            <ul>
              {draftErrors.map((error) => (
                <li key={`${error.rowIndex}-${error.field}`}>
                  Row {visibleRowNumber(error.rowIndex)}: {error.message}
                </li>
              ))}
            </ul>
          </div>
        )}
        {catalog.datasetListError && (
          <p className="text-sm text-destructive">
            Could not load the benchmarks for these tasks: {catalog.datasetListError.message}
          </p>
        )}
        <div className="py-4 overflow-y-auto max-h-[600px]">
          {rows.some((row) => row.operation !== "delete") ? (
            <EvaluationRowsTable
              rows={rows}
              catalog={catalog}
              draftErrors={draftErrors}
              errorId={errorId}
              isAdmin={isAdmin}
              showHarnessColumn={showHarnessColumn}
              onFieldChange={handleFieldChange}
              onOpenSourceChange={(index, isOpen) => updateRow(index, (row) => touched(row, { is_open: isOpen }))}
              onDelete={handleDelete}
            />
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
              onClick={() => setDraft([...rows, NEW_ROW])}
              className="flex items-center space-x-2"
            >
              <Plus className="w-4 h-4" />
              <span>Add Row</span>
            </Button>
          </div>
        </div>
      </PaperEditDialogShell>
      <SuggestTaxonomyDialog
        open={suggestionKind !== null}
        onOpenChange={(isOpen) => {
          if (!isOpen) setSuggestionKind(null);
        }}
        paperId={paperId}
        kind={suggestionKind ?? "benchmark"}
      />
    </>
  );
}

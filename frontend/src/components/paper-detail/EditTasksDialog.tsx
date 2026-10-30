import { getApiErrorMessage } from "@/lib/apiTransport";
import { paperQueryKeys } from "@/lib/paperQueryKeys";
import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Search, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { Task as APITask } from "@/lib/api/catalog.types";
import type { Paper } from "@/lib/api/papers.types";
import { catalogApi } from "@/lib/api/catalog";
import { papersApi } from "@/lib/api/papers";
import { submissionsApi } from "@/lib/api/submissions";
import { reportSubmission } from "@/lib/submissionOutcome";
import { refreshPaperQueries } from "@/lib/queryInvalidation";
import { useToast } from "@/hooks/use-toast";
import { PendingEditNotice } from "@/components/paper-detail/PendingEditNotice";
import { SuggestTaxonomyDialog } from "@/components/paper-detail/SuggestTaxonomyDialog";

interface EditTasksDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId: string;
  arxivId?: string;
  initialTaskIds: number[];
  // Minimal Task objects already attached to the paper. Used to render the
  // currently-selected chips even when they don't match the active search,
  // so the user can always uncheck a tag without first having to find it.
  initialTasks?: Array<Pick<APITask, "id" | "name" | "slug" | "description">>;
  onSuccess?: () => void;
  /** `direct` applies immediately (admin path). `pending` submits an edit for
   *  admin review without touching live data. */
  submitMode?: "direct" | "pending";
  /** When `submitMode === "pending"` and the signed-in user is a linked
   *  author of the paper, the notice copy acknowledges that. */
  isAuthor?: boolean;
}

const SEARCH_DEBOUNCE_MS = 250;
// `page_size` cap from /api/v1/tasks/ is 100; the server-side q search and
// ordering pick up everything past the alphabetical first page for us.
const SEARCH_PAGE_SIZE = 100;

export function EditTasksDialog({
  open,
  onOpenChange,
  paperId,
  arxivId,
  initialTaskIds,
  initialTasks,
  onSuccess,
  submitMode = "direct",
  isAuthor = false,
}: EditTasksDialogProps) {
  const [selectedTaskIds, setSelectedTaskIds] = useState<number[]>(initialTaskIds);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  // Pool of Task records we have full data for. Seeded with `initialTasks`
  // and grown as search results stream in, so we can always render a chip
  // for any id in `selectedTaskIds`.
  const [knownTasks, setKnownTasks] = useState<Map<number, APITask>>(new Map());
  const queryClient = useQueryClient();
  const { toast } = useToast();
  // Track whether we've already seeded state for the current "open" session.
  // The parent passes `initialTaskIds`/`initialTasks` as freshly-built arrays
  // on every render, so a naive `useEffect` that listed them as deps would
  // re-run on every background refetch and wipe the user's pending selection.
  // We only want to reset state on the false→true transition of `open`.
  const hasSeededRef = useRef(false);

  useEffect(() => {
    if (!open) {
      hasSeededRef.current = false;
      return;
    }
    if (hasSeededRef.current) return;
    hasSeededRef.current = true;
    setSelectedTaskIds(initialTaskIds);
    setSearchQuery("");
    setDebouncedQuery("");
    const seeded = new Map<number, APITask>();
    (initialTasks || []).forEach((t) => {
      const id = parseInt(t.id);
      if (!Number.isNaN(id)) {
        seeded.set(id, t as APITask);
      }
    });
    setKnownTasks(seeded);
  }, [open, initialTaskIds, initialTasks]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setDebouncedQuery(searchQuery.trim());
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [searchQuery]);

  const { data: searchData, isFetching: searchLoading } = useQuery({
    queryKey: ["tasks-search", debouncedQuery],
    queryFn: () =>
      catalogApi.listTasks({
        page_size: SEARCH_PAGE_SIZE,
        ...(debouncedQuery ? { q: debouncedQuery } : {}),
      }),
    enabled: open,
  });

  useEffect(() => {
    if (!searchData?.results?.length) return;
    setKnownTasks((prev) => {
      const next = new Map(prev);
      searchData.results.forEach((t) => {
        const id = parseInt(t.id);
        if (!Number.isNaN(id)) next.set(id, t);
      });
      return next;
    });
  }, [searchData]);

  const displayedTasks = useMemo(() => {
    const results = searchData?.results || [];
    const seen = new Set<number>();
    const ordered: APITask[] = [];
    const add = (id: number, task: APITask | undefined) => {
      if (!task || Number.isNaN(id) || seen.has(id)) return;
      ordered.push(task);
      seen.add(id);
    };
    const addSelected = () => selectedTaskIds.forEach((id) => add(id, knownTasks.get(id)));
    const addResults = () => results.forEach((t) => add(parseInt(t.id), t));
    // Without a query, pin selected tasks at the top so they can always be
    // unchecked. While searching, keep the API's relevance order first and
    // list non-matching selected tasks after the results.
    if (debouncedQuery) {
      addResults();
      addSelected();
    } else {
      addSelected();
      addResults();
    }
    return ordered;
  }, [searchData, selectedTaskIds, knownTasks, debouncedQuery]);

  const updateTasksMutation = useMutation({
    mutationFn: async ({ paperId, taskIds }: { paperId: string; taskIds: number[] }) => {
      if (submitMode === "pending") {
        const submitted = await submissionsApi.submit({
          paper_id: parseInt(paperId),
          edit_type: "tasks",
          proposed_payload: { task_ids: taskIds },
        });
        reportSubmission(submitted, {
          toast,
          queryClient,
          paperIds: [paperId, arxivId],
          queuedDescription:
            "Thanks! An admin will review your proposed task changes shortly.",
        });
        return null;
      }
      return papersApi.updateTasks(paperId, taskIds);
    },
    // Apply the new task list to the paper detail cache *before* the network
    // round-trip so the chip the user just unchecked disappears immediately.
    // The dialog also closes here, then the canonical server response
    // reconciles the cache and confirms in `onSuccess` (or rolls back on
    // `onError`).
    onMutate: async ({ taskIds }) => {
      if (submitMode === "pending") {
        // Pending submissions don't touch live data, so skip the optimistic
        // update of the paper detail cache. We still close the dialog and
        // surface a confirmation toast on success.
        return { snapshots: [] };
      }
      const optimisticTasks = taskIds
        .map((id) => knownTasks.get(id))
        .filter((t): t is APITask => Boolean(t))
        .map((t) => ({ id: t.id, name: t.name, slug: t.slug }))
        .sort((a, b) => a.name.localeCompare(b.name));
      const ids = Array.from(
        new Set(
          [paperId, arxivId].filter((v): v is string => Boolean(v)),
        ),
      );

      await Promise.all(
        ids.flatMap((id) => [
          queryClient.cancelQueries({ queryKey: paperQueryKeys.detail(id) }),
          queryClient.cancelQueries({ queryKey: paperQueryKeys.arxiv(id) }),
        ]),
      );

      const snapshots: Array<{ key: readonly unknown[]; data: Paper | undefined }> = [];
      ids.forEach((id) => {
        [paperQueryKeys.detail(id), paperQueryKeys.arxiv(id)].forEach((key) => {
          const data = queryClient.getQueryData<Paper>(key);
          snapshots.push({ key, data });
          if (data) {
            queryClient.setQueryData<Paper>(key, {
              ...data,
              tasks: optimisticTasks as unknown as Paper["tasks"],
            });
          }
        });
      });

      onSuccess?.();
      onOpenChange(false);

      return { snapshots };
    },
    onSuccess: (updatedPaper, { taskIds }) => {
      if (submitMode === "pending") {
        onSuccess?.();
        onOpenChange(false);
        return;
      }
      toast({
        title: "Tasks updated",
        description: `Saved ${taskIds.length} task${
          taskIds.length === 1 ? "" : "s"
        } for this paper.`,
      });
      if (updatedPaper) {
        refreshPaperQueries(queryClient, updatedPaper, [paperId, arxivId]);
      }
    },
    onError: (err: unknown, _vars, context) => {
      context?.snapshots?.forEach(({ key, data }) => {
        queryClient.setQueryData(key as unknown[], data);
      });

      const description = getApiErrorMessage(
        err,
        submitMode === "pending"
          ? "Failed to submit your edit. Please try again."
          : "Failed to update paper tasks.",
      );
      toast({
        title:
          submitMode === "pending"
            ? "Could not submit edit"
            : "Could not save tasks",
        description,
        variant: "destructive",
      });
    },
  });

  const handleSave = () => {
    if (
      submitMode === "direct" &&
      initialTaskIds.some((id) => !selectedTaskIds.includes(id)) &&
      !window.confirm("Remove one or more task links from this paper?")
    ) return;
    updateTasksMutation.mutate({ paperId, taskIds: selectedTaskIds });
  };

  // Treat the selection as "changed" only when it differs from what the
  // paper already has. Prevents pending-edit submissions that would be a
  // no-op and clutter the /submissions dashboard with empty cards.
  const hasChange = useMemo(() => {
    if (selectedTaskIds.length !== initialTaskIds.length) return true;
    const initialSet = new Set(initialTaskIds);
    return selectedTaskIds.some((id) => !initialSet.has(id));
  }, [selectedTaskIds, initialTaskIds]);

  const toggleTask = (taskId: number, checked: boolean) => {
    setSelectedTaskIds((prev) => {
      if (checked) {
        return prev.includes(taskId) ? prev : [...prev, taskId];
      }
      return prev.filter((id) => id !== taskId);
    });
  };

  const clearSearch = () => setSearchQuery("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[600px]">
        <DialogHeader>
          <DialogTitle>Edit Paper Tasks</DialogTitle>
          <DialogDescription>
            Select the tasks that this paper addresses. You can select multiple tasks.
          </DialogDescription>
        </DialogHeader>
        {submitMode === "pending" && <PendingEditNotice isAuthor={isAuthor} />}
        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search tasks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 pr-9"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={clearSearch}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
              aria-label="Clear search"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
        <div className="py-4 overflow-y-auto max-h-[400px]">
          {displayedTasks.length > 0 ? (
            <div className="space-y-2">
              {displayedTasks.map((task) => {
                const taskId = parseInt(task.id);
                const isSelected = selectedTaskIds.includes(taskId);
                return (
                  <div key={task.id} className="flex items-center space-x-2 p-2 hover:bg-muted/50 rounded-md">
                    <Checkbox
                      id={`task-${task.id}`}
                      checked={isSelected}
                      onCheckedChange={(checked) => toggleTask(taskId, checked === true)}
                      className="!border !border-black data-[state=checked]:!bg-black data-[state=checked]:!text-white"
                    />
                    <label
                      htmlFor={`task-${task.id}`}
                      className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer flex-1"
                    >
                      {task.name}
                      {task.description && (
                        <span className="block text-xs text-muted-foreground font-normal mt-1">
                          {task.description.substring(0, 100)}{task.description.length > 100 ? "..." : ""}
                        </span>
                      )}
                    </label>
                  </div>
                );
              })}
            </div>
          ) : searchLoading ? (
            <div className="text-center py-8 text-muted-foreground">
              <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin" />
              <p>Loading tasks...</p>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>
                {debouncedQuery
                  ? `No tasks found matching "${debouncedQuery}"`
                  : "No tasks available"}
              </p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button
            variant="ghost"
            className="sm:mr-auto"
            onClick={() => setIsSuggesting(true)}
          >
            Suggest a new task
          </Button>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={updateTasksMutation.isPending || !hasChange}
          >
            {updateTasksMutation.isPending ? (
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
        open={isSuggesting}
        onOpenChange={setIsSuggesting}
        paperId={paperId}
        kind="task"
      />
    </Dialog>
  );
}

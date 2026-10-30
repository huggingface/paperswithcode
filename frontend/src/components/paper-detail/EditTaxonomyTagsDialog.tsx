import { useEffect, useMemo, useState } from "react";
import { Loader2, Search, X } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { catalogApi } from "@/lib/api/catalog";
import type { Method, Task } from "@/lib/api/catalog.types";
import { papersApi } from "@/lib/api/papers";
import type { Paper } from "@/lib/api/papers.types";
import type { PendingEditOf } from "@/lib/pendingEdits";
import { paperQueryKeys } from "@/lib/paperQueryKeys";
import { PaperEditDialogShell } from "./PaperEditDialogShell";
import { SuggestTaxonomyDialog } from "./SuggestTaxonomyDialog";
import { usePaperSectionEdit, type PaperSectionEditorProps } from "./usePaperSectionEdit";

const SEARCH_DEBOUNCE_MS = 250;
// The catalog caps page_size at 100; the server-side q search and ordering
// reach everything past the alphabetical first page.
const SEARCH_PAGE_SIZE = 100;

interface TagKind<Item extends Task | Method> {
  editType: "tasks" | "methods";
  singular: "task" | "method";
  plural: "tasks" | "methods";
  title: string;
  description: string;
  search: (params: { page_size: number; q?: string }) => Promise<{ results: Item[] }>;
  toPendingPayload: (ids: number[]) => PendingEditOf<"tasks" | "methods">["proposed_payload"];
  applyDirect: (paperId: string, ids: number[]) => Promise<Paper>;
  /** Shows the new tags on the cached paper before the server confirms them. */
  patchPaper?: (paper: Paper, items: Item[]) => Paper;
  subtitle?: (item: Item) => string | undefined;
}

const TASK_TAGS: TagKind<Task> = {
  editType: "tasks",
  singular: "task",
  plural: "tasks",
  title: "Edit Paper Tasks",
  description: "Select the tasks that this paper addresses. You can select multiple tasks.",
  search: (params) => catalogApi.listTasks(params),
  toPendingPayload: (ids) => ({ task_ids: ids }),
  applyDirect: (paperId, ids) => papersApi.updateTasks(paperId, ids),
  patchPaper: (paper, tasks) => ({
    ...paper,
    tasks: [...tasks].sort((a, b) => a.name.localeCompare(b.name)),
  }),
};

const METHOD_TAGS: TagKind<Method> = {
  editType: "methods",
  singular: "method",
  plural: "methods",
  title: "Edit Paper Methods",
  description: "Select the methods and techniques used in this paper. You can select multiple methods.",
  search: (params) => catalogApi.listMethods(params),
  toPendingPayload: (ids) => ({ method_ids: ids }),
  applyDirect: (paperId, ids) => papersApi.updateMethods(paperId, ids),
  subtitle: (method) => (method.full_name !== method.name ? method.full_name : undefined),
};

const capitalize = (value: string) => value[0].toUpperCase() + value.slice(1);
const tagIds = (items: Array<Task | Method>) => items.map((item) => Number(item.id));

type EditTaxonomyTagsDialogProps = PaperSectionEditorProps & (
  | { kind: "task"; initialItems: Task[] }
  | { kind: "method"; initialItems: Method[] }
);

/** Edits a paper's task or method tags. */
export function EditTaxonomyTagsDialog(props: EditTaxonomyTagsDialogProps) {
  return props.kind === "task"
    ? <TaxonomyTagsEditor {...props} tagKind={TASK_TAGS} />
    : <TaxonomyTagsEditor {...props} tagKind={METHOD_TAGS} />;
}

function TaxonomyTagsEditor<Item extends Task | Method>({
  tagKind,
  onOpenChange,
  paperId,
  arxivId,
  initialItems,
  submitMode = "direct",
  isAuthor = false,
}: PaperSectionEditorProps & { tagKind: TagKind<Item>; initialItems: Item[] }) {
  const { singular, plural, patchPaper } = tagKind;
  // Selected tags keep their records so their chips survive any search.
  const [selected, setSelected] = useState<Item[]>(initialItems);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const queryClient = useQueryClient();
  const { toast } = useToast();

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setDebouncedQuery(searchQuery.trim());
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [searchQuery]);

  const { data: searchData, isFetching: searchLoading } = useQuery({
    queryKey: [`${plural}-search`, debouncedQuery],
    queryFn: () =>
      tagKind.search({
        page_size: SEARCH_PAGE_SIZE,
        ...(debouncedQuery ? { q: debouncedQuery } : {}),
      }),
  });

  const save = usePaperSectionEdit({
    editType: tagKind.editType,
    paperId,
    arxivId,
    submitMode,
    messages: {
      proposal: `${singular} changes`,
      noun: plural,
      failure: `Failed to update paper ${plural}.`,
    },
    toPendingPayload: (items: Item[]) => tagKind.toPendingPayload(tagIds(items)),
    applyDirect: (items) => tagKind.applyDirect(paperId, tagIds(items)),
    applyOptimistic: patchPaper && (async (items) => {
      const keys = [...new Set([paperId, arxivId].filter((id): id is string => Boolean(id)))]
        .flatMap((id) => [paperQueryKeys.detail(id), paperQueryKeys.arxiv(id)]);
      await Promise.all(keys.map((queryKey) => queryClient.cancelQueries({ queryKey })));
      const snapshots = keys.map((key) => ({ key, data: queryClient.getQueryData<Paper>(key) }));
      snapshots.forEach(({ key, data }) => {
        if (data) queryClient.setQueryData<Paper>(key, patchPaper(data, items));
      });
      return () => snapshots.forEach(({ key, data }) => queryClient.setQueryData(key, data));
    }),
    onSaved: (items, { direct }) => {
      if (!direct) return;
      toast({
        title: `${capitalize(plural)} updated`,
        description: `Saved ${items.length} ${items.length === 1 ? singular : plural} for this paper.`,
      });
    },
    onClose: () => onOpenChange(false),
  });

  const selectedIds = useMemo(() => new Set(tagIds(selected)), [selected]);
  const initialIds = useMemo(() => tagIds(initialItems), [initialItems]);

  const displayedItems = useMemo(() => {
    const results = searchData?.results ?? [];
    // Without a query, pin selected tags at the top so they can always be
    // unchecked. While searching, keep the API's relevance order first and
    // list non-matching selected tags after the results.
    const ordered = debouncedQuery ? [...results, ...selected] : [...selected, ...results];
    return ordered.filter((item, index) => ordered.findIndex(({ id }) => id === item.id) === index);
  }, [searchData, selected, debouncedQuery]);

  // Only a real change may be submitted; no-op pending edits clutter /submissions.
  const hasChange =
    selected.length !== initialIds.length || initialIds.some((id) => !selectedIds.has(id));

  const handleSave = () => {
    if (
      submitMode === "direct" &&
      initialIds.some((id) => !selectedIds.has(id)) &&
      !window.confirm(`Remove one or more ${singular} links from this paper?`)
    ) return;
    save.mutate(selected);
  };

  const toggle = (item: Item, checked: boolean) => {
    setSelected((current) => {
      if (!checked) return current.filter((candidate) => candidate.id !== item.id);
      return current.some((candidate) => candidate.id === item.id) ? current : [...current, item];
    });
  };

  return (
    <>
      <PaperEditDialogShell
        title={tagKind.title}
        description={tagKind.description}
        className="max-w-2xl max-h-[600px]"
        submitMode={submitMode}
        isAuthor={isAuthor}
        onOpenChange={onOpenChange}
        onSave={handleSave}
        isSaving={save.isPending}
        saveDisabled={!hasChange}
        footerStart={
          <Button variant="ghost" className="sm:mr-auto" onClick={() => setIsSuggesting(true)}>
            Suggest a new {singular}
          </Button>
        }
      >
        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder={`Search ${plural}...`}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 pr-9"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
              aria-label="Clear search"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
        <div className="py-4 overflow-y-auto max-h-[400px]">
          {displayedItems.length > 0 ? (
            <div className="space-y-2">
              {displayedItems.map((item) => {
                const subtitle = tagKind.subtitle?.(item);
                return (
                  <div key={item.id} className="flex items-center space-x-2 p-2 hover:bg-muted/50 rounded-md">
                    <Checkbox
                      id={`${singular}-${item.id}`}
                      checked={selectedIds.has(Number(item.id))}
                      onCheckedChange={(checked) => toggle(item, checked === true)}
                      className="!border !border-black data-[state=checked]:!bg-black data-[state=checked]:!text-white"
                    />
                    <label
                      htmlFor={`${singular}-${item.id}`}
                      className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer flex-1"
                    >
                      {item.name}
                      {subtitle && (
                        <span className="block text-xs text-muted-foreground font-normal">
                          {subtitle}
                        </span>
                      )}
                      {item.description && (
                        <span className="block text-xs text-muted-foreground font-normal mt-1">
                          {item.description.substring(0, 100)}{item.description.length > 100 ? "..." : ""}
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
              <p>Loading {plural}...</p>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>
                {debouncedQuery
                  ? `No ${plural} found matching "${debouncedQuery}"`
                  : `No ${plural} available`}
              </p>
            </div>
          )}
        </div>
      </PaperEditDialogShell>
      <SuggestTaxonomyDialog
        open={isSuggesting}
        onOpenChange={setIsSuggesting}
        paperId={paperId}
        kind={singular}
      />
    </>
  );
}

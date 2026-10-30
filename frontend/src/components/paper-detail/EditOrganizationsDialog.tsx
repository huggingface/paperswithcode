import { invalidatePaperDetails, invalidatePaperFeeds } from "@/lib/queryInvalidation";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, X } from "lucide-react";

import { Input } from "@/components/ui/input";
import { catalogApi } from "@/lib/api/catalog";
import { papersApi } from "@/lib/api/papers";
import { useToast } from "@/hooks/use-toast";
import { PaperEditDialogShell } from "./PaperEditDialogShell";
import { SuggestOrganizationForm } from "./SuggestOrganizationForm";
import { usePaperSectionEdit, type PaperSectionEditorProps } from "./usePaperSectionEdit";
import { catalogQueryKeys } from "@/lib/api/queryKeys";

interface Props extends PaperSectionEditorProps {
  initialOrganizationIds: number[];
}

export const EditOrganizationsDialog = ({
  onOpenChange,
  paperId,
  arxivId,
  initialOrganizationIds,
  submitMode = "direct",
  isAuthor,
}: Props) => {
  const [selected, setSelected] = useState<number[]>(initialOrganizationIds);
  const [searchQuery, setSearchQuery] = useState("");
  // "Save changes" only saves the checkboxes, so it waits while a suggestion is unsent.
  const [suggestionUnsent, setSuggestionUnsent] = useState(false);
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const organizations = useQuery({
    queryKey: [...catalogQueryKeys.organizations, "curation"],
    queryFn: () => catalogApi.organizations(false),
  });
  const displayedOrganizations = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLocaleLowerCase();
    if (!normalizedQuery) return organizations.data?.results ?? [];
    // Rank exact, prefix, and word-prefix matches above other substring
    // matches; the stable sort keeps the API's popularity order within a rank.
    const rank = (name: string) => {
      if (name === normalizedQuery) return 0;
      if (name.startsWith(normalizedQuery)) return 1;
      return name.split(/[^\p{L}\p{N}]+/u).some((word) => word.startsWith(normalizedQuery)) ? 2 : 3;
    };
    return (organizations.data?.results ?? [])
      .map((organization) => ({ organization, name: organization.name.toLocaleLowerCase() }))
      .filter(({ name }) => name.includes(normalizedQuery))
      .sort((a, b) => rank(a.name) - rank(b.name))
      .map(({ organization }) => organization);
  }, [organizations.data?.results, searchQuery]);
  const save = usePaperSectionEdit({
    editType: "organizations",
    paperId,
    arxivId,
    submitMode,
    messages: {
      proposal: "organization changes",
      noun: "organizations",
      failure: "Failed to update organizations.",
    },
    toPendingPayload: (organizationIds: number[]) => ({ organization_ids: organizationIds }),
    applyDirect: (organizationIds) => papersApi.updateOrganizations(paperId, organizationIds),
    onClose: () => onOpenChange(false),
  });
  const handleSave = () => {
    if (
      initialOrganizationIds.some((id) => !selected.includes(id)) &&
      !window.confirm(
        "Remove one or more organizations from this paper? Destructive edits may require a fresh sign-in.",
      )
    ) return;
    save.mutate(selected);
  };
  return (
    <PaperEditDialogShell
      title="Edit organizations"
      description="Associate organizations with this paper. If one is missing, search for it and suggest it for review."
      submitMode={submitMode}
      isAuthor={isAuthor}
      onOpenChange={onOpenChange}
      onSave={handleSave}
      isSaving={save.isPending}
      saveDisabled={suggestionUnsent}
    >
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          aria-label="Search organizations"
          placeholder="Search organizations..."
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          className="pl-9 pr-9"
        />
        {searchQuery && (
          <button
            type="button"
            onClick={() => setSearchQuery("")}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
            aria-label="Clear organization search"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      <div className="max-h-80 space-y-2 overflow-auto">
        {displayedOrganizations.map((organization) => {
          const id = Number(organization.id);
          return (
            <label key={organization.id} className="flex items-center gap-2 rounded border p-2">
              <input
                type="checkbox"
                checked={selected.includes(id)}
                onChange={(event) =>
                  setSelected((current) =>
                    event.target.checked
                      ? [...current, id]
                      : current.filter((value) => value !== id),
                  )
                }
              />
              {organization.name}
            </label>
          );
        })}
        {!organizations.isLoading && displayedOrganizations.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {searchQuery.trim()
              ? `No organizations found matching "${searchQuery.trim()}"`
              : "No organizations available"}
          </p>
        )}
      </div>
      {!organizations.isLoading && displayedOrganizations.length === 0 && searchQuery.trim() && (
        <SuggestOrganizationForm
          key={searchQuery.trim()}
          paperId={paperId}
          initialName={searchQuery.trim()}
          onApplied={(name) => {
            // Close: these checkboxes predate the new organization, so saving would drop it.
            onOpenChange(false);
            toast({ title: "Organization added", description: `Added "${name}" to this paper.` });
            invalidatePaperDetails(queryClient, [paperId]);
            invalidatePaperFeeds(queryClient);
            void queryClient.invalidateQueries({ queryKey: catalogQueryKeys.organizations });
          }}
          onUnsentChange={setSuggestionUnsent}
        />
      )}
      {suggestionUnsent && (
        <p className="text-sm text-muted-foreground">
          Submit the organization above, or clear the search, before saving.
        </p>
      )}
    </PaperEditDialogShell>
  );
};

import { refreshPaperQueries } from "@/lib/queryInvalidation";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { catalogApi } from "@/lib/api/catalog";
import { papersApi } from "@/lib/api/papers";
import { submissionsApi } from "@/lib/api/submissions";
import { PendingEditNotice } from "./PendingEditNotice";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId: string;
  initialOrganizationIds: number[];
  submitMode: "direct" | "pending";
  isAuthor?: boolean;
}

export const EditOrganizationsDialog = ({
  open,
  onOpenChange,
  paperId,
  initialOrganizationIds,
  submitMode,
  isAuthor,
}: Props) => {
  const [selected, setSelected] = useState<number[]>(initialOrganizationIds);
  const [searchQuery, setSearchQuery] = useState("");
  const queryClient = useQueryClient();
  useEffect(() => {
    if (open) {
      setSelected(initialOrganizationIds);
      setSearchQuery("");
    }
  }, [initialOrganizationIds, open]);
  const organizations = useQuery({
    queryKey: ["organizations", "curation"],
    queryFn: () => catalogApi.organizations(false),
    enabled: open,
  });
  const displayedOrganizations = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLocaleLowerCase();
    if (!normalizedQuery) return organizations.data?.results ?? [];
    return (organizations.data?.results ?? []).filter((organization) =>
      organization.name.toLocaleLowerCase().includes(normalizedQuery),
    );
  }, [organizations.data?.results, searchQuery]);
  const save = useMutation({
    mutationFn: async () => {
      const removes = initialOrganizationIds.some((id) => !selected.includes(id));
      if (
        removes &&
        !window.confirm(
          "Remove one or more organizations from this paper? Destructive edits may require a fresh sign-in.",
        )
      ) {
        return;
      }
      if (submitMode === "pending") {
        await submissionsApi.submit({
          paper_id: Number(paperId),
          edit_type: "organizations",
          proposed_payload: { organization_ids: selected },
        });
        return null;
      } else {
        return papersApi.updateOrganizations(paperId, selected);
      }
    },
    onSuccess: (updatedPaper) => {
      if (updatedPaper === undefined) return;
      if (updatedPaper) refreshPaperQueries(queryClient, updatedPaper, [paperId]);
      onOpenChange(false);
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit organizations</DialogTitle>
          <DialogDescription>
            Associate existing organizations with this paper. Organization creation remains admin-only.
          </DialogDescription>
        </DialogHeader>
        {submitMode === "pending" && <PendingEditNotice isAuthor={isAuthor} />}
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
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {submitMode === "pending" ? "Submit test edit" : "Save changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

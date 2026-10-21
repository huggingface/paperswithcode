import { getApiErrorMessage } from "@/lib/apiTransport";
import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Check, Plus, Trash2, Globe, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { papersApi } from "@/lib/api/papers";
import { submissionsApi } from "@/lib/api/submissions";
import { reportSubmission } from "@/lib/submissionOutcome";
import { refreshPaperQueries } from "@/lib/queryInvalidation";
import { useToast } from "@/hooks/use-toast";
import { PendingEditNotice } from "@/components/paper-detail/PendingEditNotice";

interface ProjectPage {
  url: string;
  is_official: boolean;
}

interface EditProjectPagesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId: string;
  arxivId?: string;
  initialProjectPages: ProjectPage[];
  onSuccess?: () => void;
  /** `direct` applies immediately (admin path). `pending` submits an edit for
   *  admin review without touching live data. */
  submitMode?: "direct" | "pending";
  /** When `submitMode === "pending"` and the signed-in user is a linked
   *  author of the paper, the notice copy acknowledges that. */
  isAuthor?: boolean;
}

export function EditProjectPagesDialog({
  open,
  onOpenChange,
  paperId,
  arxivId,
  initialProjectPages,
  onSuccess,
  submitMode = "direct",
  isAuthor = false,
}: EditProjectPagesDialogProps) {
  const [editedProjectPages, setEditedProjectPages] = useState<ProjectPage[]>(initialProjectPages);
  const [newProjectPageUrl, setNewProjectPageUrl] = useState("");
  const queryClient = useQueryClient();
  const { toast } = useToast();

  // Only seed local state on the false→true transition of `open` so background
  // refetches of the paper don't wipe pending edits while the dialog is open.
  const hasSeededRef = useRef(false);
  useEffect(() => {
    if (!open) {
      hasSeededRef.current = false;
      return;
    }
    if (hasSeededRef.current) return;
    hasSeededRef.current = true;
    setEditedProjectPages(initialProjectPages);
    setNewProjectPageUrl("");
  }, [open, initialProjectPages]);

  const updateProjectPagesMutation = useMutation({
    mutationFn: async ({ paperId, projectPages }: { paperId: string; projectPages: ProjectPage[] }) => {
      if (submitMode === "pending") {
        const submitted = await submissionsApi.submit({
          paper_id: parseInt(paperId),
          edit_type: "project_pages",
          proposed_payload: { project_pages: projectPages },
        });
        reportSubmission(submitted, {
          toast,
          queryClient,
          paperIds: [paperId, arxivId],
          queuedDescription:
            "Thanks! An admin will review your proposed project page changes shortly.",
        });
        return null;
      }
      return papersApi.updateProjectPages(paperId, projectPages);
    },
    onSuccess: (updatedPaper) => {
      if (submitMode === "pending") {
        onSuccess?.();
        onOpenChange(false);
        setNewProjectPageUrl("");
        return;
      }
      if (updatedPaper) {
        refreshPaperQueries(queryClient, updatedPaper, [paperId, arxivId]);
      }
      onSuccess?.();
      onOpenChange(false);
      setNewProjectPageUrl("");
    },
    onError: (err: unknown) => {
      const description = getApiErrorMessage(
        err,
        submitMode === "pending"
          ? "Failed to submit your edit. Please try again."
          : "Failed to update project pages.",
      );
      toast({
        title:
          submitMode === "pending"
            ? "Could not submit edit"
            : "Could not save project pages",
        description,
        variant: "destructive",
      });
    },
  });

  // Returns the project pages to commit, optionally folding in the typed-but-not-yet-added URL.
  // Returns null when the typed URL is a duplicate so callers can abort.
  const getProjectPagesForSubmission = (): ProjectPage[] | null => {
    const trimmedUrl = newProjectPageUrl.trim();
    if (!trimmedUrl) return editedProjectPages;

    if (editedProjectPages.some(p => p.url === trimmedUrl)) {
      alert("This project page URL is already added");
      return null;
    }

    return [...editedProjectPages, { url: trimmedUrl, is_official: false }];
  };

  const handleAddProjectPage = () => {
    const next = getProjectPagesForSubmission();
    if (next === null) return;
    if (next.length === editedProjectPages.length) return;

    setEditedProjectPages(next);
    setNewProjectPageUrl("");
  };

  const handleRemoveProjectPage = (url: string) => {
    setEditedProjectPages(editedProjectPages.filter(p => p.url !== url));
  };

  const handleToggleOfficial = (url: string) => {
    setEditedProjectPages(
      editedProjectPages.map(p =>
        p.url === url ? { ...p, is_official: !p.is_official } : p
      )
    );
  };

  const handleSave = () => {
    const next = getProjectPagesForSubmission();
    if (next === null) return;
    if (
      submitMode === "direct" &&
      initialProjectPages.some(
        (item) => !next.some((candidate) => candidate.url === item.url),
      ) &&
      !window.confirm("Remove one or more project pages from this paper?")
    ) return;
    updateProjectPagesMutation.mutate({ paperId, projectPages: next });
  };

  // Compare the edited list against the initial list (URL + is_official) so
  // we can disable submit when nothing actually changed. Includes the
  // typed-but-not-yet-added URL so users don't see a disabled button after
  // pasting a new project page.
  const hasChange = useMemo(() => {
    const trimmedNew = newProjectPageUrl.trim();
    const candidate = trimmedNew
      ? [...editedProjectPages, { url: trimmedNew, is_official: false }]
      : editedProjectPages;
    if (candidate.length !== initialProjectPages.length) return true;
    const initialMap = new Map(
      initialProjectPages.map((p) => [p.url.trim(), Boolean(p.is_official)]),
    );
    return candidate.some((p) => {
      const initial = initialMap.get(p.url.trim());
      return initial === undefined || initial !== Boolean(p.is_official);
    });
  }, [editedProjectPages, newProjectPageUrl, initialProjectPages]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[600px]">
        <DialogHeader>
          <DialogTitle>Edit Paper Project Pages</DialogTitle>
          <DialogDescription>
            Add or remove project page URLs (e.g. authors' demo or landing pages) associated with this paper. Mark pages as official if they are created by the paper authors.
          </DialogDescription>
        </DialogHeader>
        {submitMode === "pending" && <PendingEditNotice isAuthor={isAuthor} />}

        <div className="space-y-2">
          <label className="text-sm font-medium">Add Project Page URL</label>
          <div className="flex space-x-2">
            <Input
              type="url"
              placeholder="https://example.com/project"
              value={newProjectPageUrl}
              onChange={(e) => setNewProjectPageUrl(e.target.value)}
              onKeyPress={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAddProjectPage();
                }
              }}
              className="flex-1"
            />
            <Button onClick={handleAddProjectPage} size="sm" disabled={!newProjectPageUrl.trim()}>
              <Plus className="w-4 h-4 mr-1" />
              Add
            </Button>
          </div>
        </div>

        <div className="py-4 overflow-y-auto max-h-[350px]">
          {editedProjectPages.length > 0 ? (
            <div className="space-y-2">
              {editedProjectPages.map((page, index) => (
                <div key={index} className="flex items-center space-x-2 p-3 bg-muted/30 rounded-lg hover:bg-muted/50 transition-colors">
                  <Globe className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-2">
                      <span className="text-sm font-medium text-paper-blue truncate">
                        {page.url}
                      </span>
                      {page.is_official && (
                        <Badge variant="secondary" className="text-xs">Official</Badge>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center space-x-1">
                    <Button
                      variant={page.is_official ? "default" : "outline"}
                      size="sm"
                      onClick={() => handleToggleOfficial(page.url)}
                      className="h-8 px-2 text-xs"
                      title={
                        page.is_official
                          ? "Click to unmark as official (created by paper authors)"
                          : "Click to mark as official (created by paper authors)"
                      }
                    >
                      <Star
                        className={`w-3.5 h-3.5 mr-1 ${page.is_official ? "fill-current" : ""}`}
                      />
                      {page.is_official ? "Official" : "Mark official"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveProjectPage(page.url)}
                      className="h-8 px-2 text-destructive hover:text-destructive"
                      title="Remove project page"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Globe className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No project pages added yet</p>
              <p className="text-xs mt-1">Add a project page URL above to get started</p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={updateProjectPagesMutation.isPending || !hasChange}
          >
            {updateProjectPagesMutation.isPending ? (
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
    </Dialog>
  );
}

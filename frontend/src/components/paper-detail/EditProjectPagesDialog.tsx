import { useMemo, useState } from "react";
import { Plus, Trash2, Globe, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { papersApi } from "@/lib/api/papers";
import type { UrlItem as ProjectPage } from "@/lib/pendingEdits";
import { PaperEditDialogShell } from "./PaperEditDialogShell";
import { usePaperSectionEdit, type PaperSectionEditorProps } from "./usePaperSectionEdit";

interface EditProjectPagesDialogProps extends PaperSectionEditorProps {
  initialProjectPages: ProjectPage[];
}

export function EditProjectPagesDialog({
  onOpenChange,
  paperId,
  arxivId,
  initialProjectPages,
  submitMode = "direct",
  isAuthor = false,
}: EditProjectPagesDialogProps) {
  const [editedProjectPages, setEditedProjectPages] = useState<ProjectPage[]>(initialProjectPages);
  const [newProjectPageUrl, setNewProjectPageUrl] = useState("");
  const save = usePaperSectionEdit({
    editType: "project_pages",
    paperId,
    arxivId,
    submitMode,
    messages: {
      proposal: "project page changes",
      noun: "project pages",
      failure: "Failed to update project pages.",
    },
    toPendingPayload: (projectPages: ProjectPage[]) => ({ project_pages: projectPages }),
    applyDirect: (projectPages) => papersApi.updateProjectPages(paperId, projectPages),
    onClose: () => onOpenChange(false),
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
    save.mutate(next);
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
    <PaperEditDialogShell
      title="Edit Paper Project Pages"
      description="Add or remove project page URLs (e.g. authors' demo or landing pages) associated with this paper. Mark pages as official if they are created by the paper authors."
      className="max-w-2xl max-h-[600px]"
      submitMode={submitMode}
      isAuthor={isAuthor}
      onOpenChange={onOpenChange}
      onSave={handleSave}
      isSaving={save.isPending}
      saveDisabled={!hasChange}
    >
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
    </PaperEditDialogShell>
  );
}

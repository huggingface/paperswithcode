import { useMemo, useState } from "react";
import { Plus, Trash2, Github, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { papersApi } from "@/lib/api/papers";
import type { UrlItem as Repository } from "@/lib/pendingEdits";
import { githubUrlsMatch, normalizeGithubUrl } from "@/lib/github";
import { PaperEditDialogShell } from "./PaperEditDialogShell";
import { usePaperSectionEdit, type PaperSectionEditorProps } from "./usePaperSectionEdit";

interface EditRepositoriesDialogProps extends PaperSectionEditorProps {
  initialRepositories: Repository[];
}

export function EditRepositoriesDialog({
  onOpenChange,
  paperId,
  arxivId,
  initialRepositories,
  submitMode = "direct",
  isAuthor = false,
}: EditRepositoriesDialogProps) {
  const [editedRepositories, setEditedRepositories] = useState<Repository[]>(initialRepositories);
  const [newRepositoryUrl, setNewRepositoryUrl] = useState("");
  const save = usePaperSectionEdit({
    editType: "repositories",
    paperId,
    arxivId,
    submitMode,
    messages: {
      proposal: "repository changes",
      noun: "repositories",
      failure: "Failed to update paper repositories.",
    },
    toPendingPayload: (repositories: Repository[]) => ({ repositories }),
    applyDirect: (repositories) => papersApi.updateRepositories(paperId, repositories),
    onClose: () => onOpenChange(false),
  });

  const dedupeRepositories = (repos: Repository[]): Repository[] => {
    const merged: Repository[] = [];
    for (const repo of repos) {
      const existing = merged.find((r) => githubUrlsMatch(r.url, repo.url));
      if (existing) {
        existing.is_official = existing.is_official || repo.is_official;
      } else {
        const normalized = normalizeGithubUrl(repo.url);
        merged.push({
          url: normalized ?? repo.url.trim(),
          is_official: repo.is_official,
        });
      }
    }
    return merged;
  };

  // Returns the repositories to commit, optionally folding in the typed-but-not-yet-added URL.
  // Returns null when the typed URL is a duplicate so callers can abort.
  const getRepositoriesForSubmission = (): Repository[] | null => {
    const trimmedUrl = newRepositoryUrl.trim();
    const base = trimmedUrl
      ? [...editedRepositories, { url: trimmedUrl, is_official: false }]
      : editedRepositories;

    if (
      trimmedUrl &&
      editedRepositories.some((r) => githubUrlsMatch(r.url, trimmedUrl))
    ) {
      alert("This repository URL is already added");
      return null;
    }

    return dedupeRepositories(base);
  };

  const handleAddRepository = () => {
    const next = getRepositoriesForSubmission();
    if (next === null) return;
    if (next.length === editedRepositories.length) return;

    setEditedRepositories(next);
    setNewRepositoryUrl("");
  };

  const handleRemoveRepository = (url: string) => {
    setEditedRepositories(editedRepositories.filter(r => r.url !== url));
  };

  const handleToggleOfficial = (url: string) => {
    setEditedRepositories(
      editedRepositories.map(r =>
        r.url === url ? { ...r, is_official: !r.is_official } : r
      )
    );
  };

  const handleSave = () => {
    const next = getRepositoriesForSubmission();
    if (next === null) return;
    if (
      submitMode === "direct" &&
      initialRepositories.some(
        (item) => !next.some((candidate) => candidate.url === item.url),
      ) &&
      !window.confirm("Remove one or more repositories from this paper?")
    ) return;
    save.mutate(next);
  };

  // Compare the edited list against the initial list (URL + is_official) so
  // we can disable submit when nothing actually changed. Includes the
  // typed-but-not-yet-added URL so users don't see a disabled button after
  // pasting a new repo.
  const hasChange = useMemo(() => {
    const trimmedNew = newRepositoryUrl.trim();
    const candidate = trimmedNew
      ? [...editedRepositories, { url: trimmedNew, is_official: false }]
      : editedRepositories;
    if (candidate.length !== initialRepositories.length) return true;
    const initial = dedupeRepositories(initialRepositories);
    const proposed = dedupeRepositories(candidate);
    if (proposed.length !== initial.length) return true;
    const initialMap = new Map(
      initial.map((r) => [
        normalizeGithubUrl(r.url) ?? r.url.trim(),
        Boolean(r.is_official),
      ]),
    );
    return proposed.some((r) => {
      const key = normalizeGithubUrl(r.url) ?? r.url.trim();
      const prev = initialMap.get(key);
      return prev === undefined || prev !== Boolean(r.is_official);
    });
  }, [editedRepositories, newRepositoryUrl, initialRepositories]);

  return (
    <PaperEditDialogShell
      title="Edit Paper Repositories"
      description="Add or remove GitHub repository URLs associated with this paper. Mark repositories as official if they are created by the paper authors."
      className="max-w-2xl max-h-[600px]"
      submitMode={submitMode}
      isAuthor={isAuthor}
      onOpenChange={onOpenChange}
      onSave={handleSave}
      isSaving={save.isPending}
      saveDisabled={!hasChange}
    >
      {/* Add new repository */}
      <div className="space-y-2">
        <label className="text-sm font-medium">Add Repository URL</label>
        <div className="flex space-x-2">
          <Input
            type="url"
            placeholder="https://github.com/owner/repo"
            value={newRepositoryUrl}
            onChange={(e) => setNewRepositoryUrl(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleAddRepository();
              }
            }}
            className="flex-1"
          />
          <Button onClick={handleAddRepository} size="sm" disabled={!newRepositoryUrl.trim()}>
            <Plus className="w-4 h-4 mr-1" />
            Add
          </Button>
        </div>
      </div>

      {/* List of repositories */}
      <div className="py-4 overflow-y-auto max-h-[350px]">
        {editedRepositories.length > 0 ? (
          <div className="space-y-2">
            {editedRepositories.map((repo, index) => (
              <div key={index} className="flex items-center space-x-2 p-3 bg-muted/30 rounded-lg hover:bg-muted/50 transition-colors">
                <Github className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-medium text-paper-blue truncate">
                      {repo.url}
                    </span>
                    {repo.is_official && (
                      <Badge variant="secondary" className="text-xs">Official</Badge>
                    )}
                  </div>
                </div>
                <div className="flex items-center space-x-1">
                  <Button
                    variant={repo.is_official ? "default" : "outline"}
                    size="sm"
                    onClick={() => handleToggleOfficial(repo.url)}
                    className="h-8 px-2 text-xs"
                    title={
                      repo.is_official
                        ? "Click to unmark as official (created by paper authors)"
                        : "Click to mark as official (created by paper authors)"
                    }
                  >
                    <Star
                      className={`w-3.5 h-3.5 mr-1 ${repo.is_official ? "fill-current" : ""}`}
                    />
                    {repo.is_official ? "Official" : "Mark official"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleRemoveRepository(repo.url)}
                    className="h-8 px-2 text-destructive hover:text-destructive"
                    title="Remove repository"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <Github className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No repositories added yet</p>
            <p className="text-xs mt-1">Add a repository URL above to get started</p>
          </div>
        )}
      </div>
    </PaperEditDialogShell>
  );
}

import { useState } from "react";
import { Github, Globe, Plus, Star, Trash2, type LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { papersApi } from "@/lib/api/papers";
import { normalizeGithubUrl } from "@/lib/github";
import type { Paper } from "@/lib/api/papers.types";
import type { UrlItem } from "@/lib/pendingEdits";
import { PaperEditDialogShell } from "./PaperEditDialogShell";
import { usePaperSectionEdit, type PaperSectionEditorProps } from "./usePaperSectionEdit";

/** Paper sections edited as a list of URLs, each optionally marked official. */
const URL_LISTS = {
  repositories: {
    /** GitHub URLs compare by owner/repo; anything else by its trimmed text. */
    canonical: (url: string) => normalizeGithubUrl(url) ?? url.trim(),
    toPayload: (repositories: UrlItem[]) => ({ repositories }),
    update: (paperId: string, items: UrlItem[]) => papersApi.updateRepositories(paperId, items),
    icon: Github,
    title: "Edit Paper Repositories",
    description:
      "Add or remove GitHub repository URLs associated with this paper. Mark repositories as official if they are created by the paper authors.",
    addLabel: "Add Repository URL",
    placeholder: "https://github.com/owner/repo",
    singular: "repository",
    plural: "repositories",
    failure: "Failed to update paper repositories.",
  },
  project_pages: {
    canonical: (url: string) => url.trim(),
    toPayload: (projectPages: UrlItem[]) => ({ project_pages: projectPages }),
    update: (paperId: string, items: UrlItem[]) => papersApi.updateProjectPages(paperId, items),
    icon: Globe,
    title: "Edit Paper Project Pages",
    description:
      "Add or remove project page URLs (e.g. authors' demo or landing pages) associated with this paper. Mark pages as official if they are created by the paper authors.",
    addLabel: "Add Project Page URL",
    placeholder: "https://example.com/project",
    singular: "project page",
    plural: "project pages",
    failure: "Failed to update project pages.",
  },
} satisfies Record<string, {
  canonical: (url: string) => string;
  toPayload: (items: UrlItem[]) => unknown;
  update: (paperId: string, items: UrlItem[]) => Promise<Paper>;
  icon: LucideIcon;
  title: string;
  description: string;
  addLabel: string;
  placeholder: string;
  singular: string;
  plural: string;
  failure: string;
}>;

export type UrlListKind = keyof typeof URL_LISTS;

interface EditUrlListDialogProps extends PaperSectionEditorProps {
  kind: UrlListKind;
  initialItems: UrlItem[];
}

export function EditUrlListDialog({
  kind,
  onOpenChange,
  paperId,
  arxivId,
  initialItems,
  submitMode = "direct",
  isAuthor = false,
}: EditUrlListDialogProps) {
  const list = URL_LISTS[kind];
  const Icon = list.icon;
  const [items, setItems] = useState<UrlItem[]>(initialItems);
  const [newUrl, setNewUrl] = useState("");

  // Canonical URLs, with one entry per URL; a merged entry is official if any copy was.
  const dedupe = (candidates: UrlItem[]): UrlItem[] => {
    const merged = new Map<string, UrlItem>();
    for (const { url, is_official } of candidates) {
      const key = list.canonical(url);
      const existing = merged.get(key);
      merged.set(key, { url: key, is_official: Boolean(existing?.is_official || is_official) });
    }
    return [...merged.values()];
  };
  const keys = (candidates: UrlItem[]) => new Set(candidates.map(({ url }) => list.canonical(url)));

  const save = usePaperSectionEdit({
    editType: kind,
    paperId,
    arxivId,
    submitMode,
    messages: { proposal: `${list.singular} changes`, noun: list.plural, failure: list.failure },
    toPendingPayload: list.toPayload,
    applyDirect: (next: UrlItem[]) => list.update(paperId, next),
    onClose: () => onOpenChange(false),
    removal: {
      removes: (next) => {
        const kept = keys(next);
        return initialItems.some(({ url }) => !kept.has(list.canonical(url)));
      },
      prompt: `Remove one or more ${list.plural} from this paper?`,
    },
  });

  // The typed-but-not-yet-added URL counts as added, so pasting and saving works.
  const typed = newUrl.trim();
  const candidate = typed ? [...items, { url: typed, is_official: false }] : items;

  // The list to commit, or null when the typed URL is already listed.
  const itemsForSubmission = (): UrlItem[] | null => {
    if (typed && keys(items).has(list.canonical(typed))) {
      alert(`This ${list.singular} URL is already added`);
      return null;
    }
    return dedupe(candidate);
  };

  const handleAdd = () => {
    const next = itemsForSubmission();
    if (next === null || next.length === items.length) return;
    setItems(next);
    setNewUrl("");
  };

  const handleSave = () => {
    const next = itemsForSubmission();
    if (next !== null) save.submit(next);
  };

  // Only a real change (a URL or an official flag) may be submitted.
  const initial = new Map(dedupe(initialItems).map(({ url, is_official }) => [url, is_official]));
  const proposed = dedupe(candidate);
  const hasChange =
    candidate.length !== initialItems.length ||
    proposed.length !== initial.size ||
    proposed.some(({ url, is_official }) => initial.get(url) !== is_official);

  return (
    <PaperEditDialogShell
      title={list.title}
      description={list.description}
      className="max-w-2xl max-h-[600px]"
      submitMode={submitMode}
      isAuthor={isAuthor}
      onOpenChange={onOpenChange}
      onSave={handleSave}
      isSaving={save.isPending}
      saveDisabled={!hasChange}
    >
      <div className="space-y-2">
        <label className="text-sm font-medium">{list.addLabel}</label>
        <div className="flex space-x-2">
          <Input
            type="url"
            placeholder={list.placeholder}
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleAdd();
              }
            }}
            className="flex-1"
          />
          <Button onClick={handleAdd} size="sm" disabled={!typed}>
            <Plus className="w-4 h-4 mr-1" />
            Add
          </Button>
        </div>
      </div>

      <div className="py-4 overflow-y-auto max-h-[350px]">
        {items.length > 0 ? (
          <div className="space-y-2">
            {items.map((item, index) => (
              <div key={index} className="flex items-center space-x-2 p-3 bg-muted/30 rounded-lg hover:bg-muted/50 transition-colors">
                <Icon className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-medium text-paper-blue truncate">{item.url}</span>
                    {item.is_official && <Badge variant="secondary" className="text-xs">Official</Badge>}
                  </div>
                </div>
                <div className="flex items-center space-x-1">
                  <Button
                    variant={item.is_official ? "default" : "outline"}
                    size="sm"
                    onClick={() => setItems(items.map((i) => (i.url === item.url ? { ...i, is_official: !i.is_official } : i)))}
                    className="h-8 px-2 text-xs"
                    title={
                      item.is_official
                        ? "Click to unmark as official (created by paper authors)"
                        : "Click to mark as official (created by paper authors)"
                    }
                  >
                    <Star className={`w-3.5 h-3.5 mr-1 ${item.is_official ? "fill-current" : ""}`} />
                    {item.is_official ? "Official" : "Mark official"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setItems(items.filter((i) => i.url !== item.url))}
                    className="h-8 px-2 text-destructive hover:text-destructive"
                    title={`Remove ${list.singular}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <Icon className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No {list.plural} added yet</p>
            <p className="text-xs mt-1">Add a {list.singular} URL above to get started</p>
          </div>
        )}
      </div>
    </PaperEditDialogShell>
  );
}

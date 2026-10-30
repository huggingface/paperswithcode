import { useMemo, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { papersApi } from "@/lib/api/papers";
import type { PendingEditOf } from "@/lib/pendingEdits";
import { PaperEditDialogShell } from "./PaperEditDialogShell";
import { usePaperSectionEdit, type PaperSectionEditorProps } from "./usePaperSectionEdit";

type HfArtifactsPayload = PendingEditOf<"hf_artifacts">["proposed_payload"];

interface EditHfArtifactsDialogProps extends PaperSectionEditorProps {
  initialArtifacts: HfArtifactsPayload;
}

type ArtifactBucket = keyof HfArtifactsPayload;

const BUCKET_CONFIG: Array<{
  key: ArtifactBucket;
  label: string;
  placeholder: string;
}> = [
  {
    key: "hf_models",
    label: "Models",
    placeholder: "https://huggingface.co/org/model",
  },
  {
    key: "hf_datasets",
    label: "Datasets",
    placeholder: "https://huggingface.co/datasets/org/data",
  },
  {
    key: "hf_spaces",
    label: "Spaces",
    placeholder: "https://huggingface.co/spaces/org/demo",
  },
];

function normalizeUrlList(urls: string[]): string[] {
  return urls.map((url) => url.trim()).filter(Boolean);
}

function listsEqual(a: string[], b: string[]): boolean {
  const left = normalizeUrlList(a).sort();
  const right = normalizeUrlList(b).sort();
  if (left.length !== right.length) return false;
  return left.every((value, index) => value === right[index]);
}

function payloadsEqual(a: HfArtifactsPayload, b: HfArtifactsPayload): boolean {
  return (
    listsEqual(a.hf_models, b.hf_models) &&
    listsEqual(a.hf_datasets, b.hf_datasets) &&
    listsEqual(a.hf_spaces, b.hf_spaces)
  );
}

export function EditHfArtifactsDialog({
  onOpenChange,
  paperId,
  arxivId,
  initialArtifacts,
  submitMode = "direct",
  isAuthor = false,
}: EditHfArtifactsDialogProps) {
  const [editedArtifacts, setEditedArtifacts] = useState<HfArtifactsPayload>(initialArtifacts);
  const [newUrls, setNewUrls] = useState<Record<ArtifactBucket, string>>({
    hf_models: "",
    hf_datasets: "",
    hf_spaces: "",
  });
  const save = usePaperSectionEdit({
    editType: "hf_artifacts",
    paperId,
    arxivId,
    submitMode,
    messages: {
      proposal: "Hugging Face artifact changes",
      noun: "Hugging Face artifacts",
      failure: "Failed to update Hugging Face artifacts.",
    },
    toPendingPayload: (artifacts: HfArtifactsPayload) => artifacts,
    applyDirect: (artifacts) => papersApi.updateHfArtifacts(paperId, artifacts),
    onClose: () => onOpenChange(false),
  });

  const getArtifactsForSubmission = (): HfArtifactsPayload | null => {
    const next: HfArtifactsPayload = {
      hf_models: [...editedArtifacts.hf_models],
      hf_datasets: [...editedArtifacts.hf_datasets],
      hf_spaces: [...editedArtifacts.hf_spaces],
    };

    for (const { key } of BUCKET_CONFIG) {
      const trimmedUrl = newUrls[key].trim();
      if (!trimmedUrl) continue;
      if (next[key].some((url) => url.trim() === trimmedUrl)) {
        alert(`This ${key.replace("hf_", "")} URL is already added`);
        return null;
      }
      next[key] = [...next[key], trimmedUrl];
    }

    return next;
  };

  const handleAddUrl = (bucket: ArtifactBucket) => {
    const trimmedUrl = newUrls[bucket].trim();
    if (!trimmedUrl) return;
    if (editedArtifacts[bucket].some((url) => url.trim() === trimmedUrl)) {
      alert(`This ${bucket.replace("hf_", "")} URL is already added`);
      return;
    }
    setEditedArtifacts((prev) => ({
      ...prev,
      [bucket]: [...prev[bucket], trimmedUrl],
    }));
    setNewUrls((prev) => ({ ...prev, [bucket]: "" }));
  };

  const handleRemoveUrl = (bucket: ArtifactBucket, url: string) => {
    setEditedArtifacts((prev) => ({
      ...prev,
      [bucket]: prev[bucket].filter((item) => item !== url),
    }));
  };

  const handleSave = () => {
    const next = getArtifactsForSubmission();
    if (next === null) return;
    const removes = (Object.keys(initialArtifacts) as ArtifactBucket[]).some(
      (bucket) =>
        initialArtifacts[bucket].some(
          (url) => !next[bucket].includes(url),
        ),
    );
    if (
      submitMode === "direct" &&
      removes &&
      !window.confirm("Remove one or more Hugging Face artifact links?")
    ) return;
    save.mutate(next);
  };

  const hasChange = useMemo(() => {
    const next: HfArtifactsPayload = {
      hf_models: [...editedArtifacts.hf_models],
      hf_datasets: [...editedArtifacts.hf_datasets],
      hf_spaces: [...editedArtifacts.hf_spaces],
    };

    for (const { key } of BUCKET_CONFIG) {
      const trimmedUrl = newUrls[key].trim();
      if (!trimmedUrl) continue;
      if (next[key].some((url) => url.trim() === trimmedUrl)) {
        return false;
      }
      next[key] = [...next[key], trimmedUrl];
    }

    return !payloadsEqual(next, initialArtifacts);
  }, [editedArtifacts, newUrls, initialArtifacts]);

  return (
    <PaperEditDialogShell
      title="Edit Hugging Face Artifacts"
      description="Add or remove linked Hugging Face models, datasets, and Spaces for this paper."
      className="max-w-2xl max-h-[700px]"
      submitMode={submitMode}
      isAuthor={isAuthor}
      onOpenChange={onOpenChange}
      onSave={handleSave}
      isSaving={save.isPending}
      saveDisabled={!hasChange}
    >
      <div className="space-y-6 py-2 overflow-y-auto max-h-[460px]">
        {BUCKET_CONFIG.map(({ key, label, placeholder }) => (
          <div key={key} className="space-y-2">
            <label className="text-sm font-medium">{label}</label>
            <div className="flex space-x-2">
              <Input
                type="url"
                placeholder={placeholder}
                value={newUrls[key]}
                onChange={(e) =>
                  setNewUrls((prev) => ({ ...prev, [key]: e.target.value }))
                }
                onKeyPress={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAddUrl(key);
                  }
                }}
                className="flex-1"
              />
              <Button onClick={() => handleAddUrl(key)} size="sm" disabled={!newUrls[key].trim()}>
                <Plus className="w-4 h-4 mr-1" />
                Add
              </Button>
            </div>
            {editedArtifacts[key].length > 0 ? (
              <div className="space-y-2">
                {editedArtifacts[key].map((url) => (
                  <div
                    key={url}
                    className="flex items-center space-x-2 p-3 bg-muted/30 rounded-lg hover:bg-muted/50 transition-colors"
                  >
                    <span className="text-sm font-medium text-paper-blue truncate flex-1">
                      {url}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveUrl(key, url)}
                      className="h-8 px-2 text-destructive hover:text-destructive"
                      title={`Remove ${label.toLowerCase()} URL`}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-muted-foreground">No {label.toLowerCase()} linked yet.</div>
            )}
          </div>
        ))}
      </div>
    </PaperEditDialogShell>
  );
}

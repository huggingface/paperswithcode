import { getApiErrorMessage } from "@/lib/apiTransport";
import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Check, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { papersApi } from "@/lib/api/papers";
import { submissionsApi } from "@/lib/api/submissions";
import { refreshPaperQueries } from "@/lib/queryInvalidation";
import { useToast } from "@/hooks/use-toast";
import { PendingEditNotice } from "@/components/paper-detail/PendingEditNotice";

export interface HfArtifactsPayload {
  hf_models: string[];
  hf_datasets: string[];
  hf_spaces: string[];
}

interface EditHfArtifactsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId: string;
  arxivId?: string;
  initialArtifacts: HfArtifactsPayload;
  onSuccess?: () => void;
  submitMode?: "direct" | "pending";
  isAuthor?: boolean;
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
  open,
  onOpenChange,
  paperId,
  arxivId,
  initialArtifacts,
  onSuccess,
  submitMode = "direct",
  isAuthor = false,
}: EditHfArtifactsDialogProps) {
  const [editedArtifacts, setEditedArtifacts] = useState<HfArtifactsPayload>(initialArtifacts);
  const [newUrls, setNewUrls] = useState<Record<ArtifactBucket, string>>({
    hf_models: "",
    hf_datasets: "",
    hf_spaces: "",
  });
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const hasSeededRef = useRef(false);
  useEffect(() => {
    if (!open) {
      hasSeededRef.current = false;
      return;
    }
    if (hasSeededRef.current) return;
    hasSeededRef.current = true;
    setEditedArtifacts(initialArtifacts);
    setNewUrls({ hf_models: "", hf_datasets: "", hf_spaces: "" });
  }, [open, initialArtifacts]);

  const updateArtifactsMutation = useMutation({
    mutationFn: async ({ paperId, artifacts }: { paperId: string; artifacts: HfArtifactsPayload }) => {
      if (submitMode === "pending") {
        await submissionsApi.submit({
          paper_id: parseInt(paperId),
          edit_type: "hf_artifacts",
          proposed_payload: artifacts,
        });
        return null;
      }
      return papersApi.updateHfArtifacts(paperId, artifacts);
    },
    onSuccess: (updatedPaper) => {
      if (submitMode === "pending") {
        toast({
          title: "Edit submitted for review",
          description:
            "Thanks! An admin will review your proposed Hugging Face artifact changes shortly.",
        });
        onSuccess?.();
        onOpenChange(false);
        setNewUrls({ hf_models: "", hf_datasets: "", hf_spaces: "" });
        return;
      }
      if (updatedPaper) {
        refreshPaperQueries(queryClient, updatedPaper, [paperId, arxivId]);
      }
      onSuccess?.();
      onOpenChange(false);
      setNewUrls({ hf_models: "", hf_datasets: "", hf_spaces: "" });
    },
    onError: (err: unknown) => {
      const description = getApiErrorMessage(
        err,
        submitMode === "pending"
          ? "Failed to submit your edit. Please try again."
          : "Failed to update Hugging Face artifacts.",
      );
      toast({
        title:
          submitMode === "pending"
            ? "Could not submit edit"
            : "Could not save Hugging Face artifacts",
        description,
        variant: "destructive",
      });
    },
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
    updateArtifactsMutation.mutate({ paperId, artifacts: next });
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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[700px]">
        <DialogHeader>
          <DialogTitle>Edit Hugging Face Artifacts</DialogTitle>
          <DialogDescription>
            Add or remove linked Hugging Face models, datasets, and Spaces for this paper.
          </DialogDescription>
        </DialogHeader>
        {submitMode === "pending" && <PendingEditNotice isAuthor={isAuthor} />}

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

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={updateArtifactsMutation.isPending || !hasChange}
          >
            {updateArtifactsMutation.isPending ? (
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

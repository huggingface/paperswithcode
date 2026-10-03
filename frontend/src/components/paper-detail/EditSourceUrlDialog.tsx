import { getApiErrorMessage } from "@/lib/apiTransport";
import { useEffect, useRef, useState } from "react";
import { Loader2, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { papersApi } from "@/lib/api/papers";
import { submissionsApi } from "@/lib/api/submissions";
import { refreshPaperQueries } from "@/lib/queryInvalidation";
import { useToast } from "@/hooks/use-toast";
import { PendingEditNotice } from "@/components/paper-detail/PendingEditNotice";

interface EditSourceUrlDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId: string;
  arxivId?: string;
  initialUrl: string;
  onSuccess?: () => void;
  /** `direct` applies immediately (admin path). `pending` submits an edit for
   *  admin review without touching live data. */
  submitMode?: "direct" | "pending";
  /** When `submitMode === "pending"` and the signed-in user is a linked
   *  author of the paper, the notice copy acknowledges that. */
  isAuthor?: boolean;
}

export function EditSourceUrlDialog({
  open,
  onOpenChange,
  paperId,
  arxivId,
  initialUrl,
  onSuccess,
  submitMode = "direct",
  isAuthor = false,
}: EditSourceUrlDialogProps) {
  const [editedUrl, setEditedUrl] = useState(initialUrl);
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
    setEditedUrl(initialUrl);
  }, [open, initialUrl]);

  const updateSourceUrlMutation = useMutation({
    mutationFn: async ({ paperId, sourceUrl }: { paperId: string; sourceUrl: string }) => {
      if (submitMode === "pending") {
        await submissionsApi.submit({
          paper_id: parseInt(paperId),
          edit_type: "source_url",
          proposed_payload: { source_url: sourceUrl },
        });
        return null;
      }
      return papersApi.updateSourceUrl(paperId, sourceUrl);
    },
    onSuccess: (updatedPaper) => {
      if (submitMode === "pending") {
        toast({
          title: "Edit submitted for review",
          description:
            "Thanks! An admin will review your proposed source URL change shortly.",
        });
        onSuccess?.();
        onOpenChange(false);
        return;
      }
      if (updatedPaper) {
        refreshPaperQueries(queryClient, updatedPaper, [paperId, arxivId]);
      }
      onSuccess?.();
      onOpenChange(false);
    },
    onError: (err: unknown) => {
      const description = getApiErrorMessage(
        err,
        submitMode === "pending"
          ? "Failed to submit your edit. Please try again."
          : "Failed to update source URL.",
      );
      toast({
        title:
          submitMode === "pending"
            ? "Could not submit edit"
            : "Could not save source URL",
        description,
        variant: "destructive",
      });
    },
  });

  const trimmed = editedUrl.trim();
  const isValidUrl = /^https?:\/\//i.test(trimmed);
  const hasChange = trimmed !== (initialUrl || "").trim();

  const handleSave = () => {
    if (!isValidUrl) return;
    updateSourceUrlMutation.mutate({ paperId, sourceUrl: trimmed });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit Source URL</DialogTitle>
          <DialogDescription>
            Update the canonical URL for this external paper. This is the page the {`"Source page"`} button links to. ArXiv papers cannot edit this field.
          </DialogDescription>
        </DialogHeader>
        {submitMode === "pending" && <PendingEditNotice isAuthor={isAuthor} />}

        <div className="space-y-2 py-2">
          <label className="text-sm font-medium">Source URL</label>
          <Input
            type="url"
            placeholder="https://example.com/paper"
            value={editedUrl}
            onChange={(e) => setEditedUrl(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === "Enter" && isValidUrl && hasChange) {
                e.preventDefault();
                handleSave();
              }
            }}
          />
          {!isValidUrl && trimmed.length > 0 && (
            <p className="text-xs text-destructive">
              URL must start with http:// or https://
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={
              updateSourceUrlMutation.isPending || !isValidUrl || !hasChange
            }
          >
            {updateSourceUrlMutation.isPending ? (
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

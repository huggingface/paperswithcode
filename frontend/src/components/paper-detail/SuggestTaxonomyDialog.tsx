import { useEffect, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useMutation } from "@tanstack/react-query";
import { submitPendingPaperEdit, type PendingEditType } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

type TaxonomyKind = "task" | "method" | "benchmark" | "metric" | "conference";

interface SuggestTaxonomyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Omitted for suggestions submitted from a taxonomy directory page. */
  paperId?: string;
  kind: TaxonomyKind;
}

const NAME_MAX = 200;
const DESCRIPTION_MAX = 2000;

const KIND_EDIT_TYPE: Record<TaxonomyKind, PendingEditType> = {
  task: "new_task",
  method: "new_method",
  benchmark: "new_benchmark",
  metric: "new_metric",
  conference: "new_conference",
};

const KIND_NAME_PLACEHOLDER: Record<TaxonomyKind, string> = {
  task: "e.g. Long-context Retrieval",
  method: "e.g. Rotary Position Embedding",
  benchmark: "e.g. ImageNet (ReaL)",
  metric: "e.g. Top-5 Accuracy",
  conference: "e.g. International Conference on Machine Learning 2027",
};

const KIND_DESCRIPTION_PLACEHOLDER: Record<TaxonomyKind, string> = {
  task: "Briefly describe this task and what it covers.",
  method: "Briefly describe this method and what it covers.",
  benchmark:
    "Briefly describe this benchmark, the task it belongs to, and where it comes from.",
  metric:
    "Briefly describe this metric and whether higher or lower is better.",
  conference:
    "Briefly describe this conference, including its research focus and edition.",
};

export function SuggestTaxonomyDialog({
  open,
  onOpenChange,
  paperId,
  kind,
}: SuggestTaxonomyDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const { toast } = useToast();

  const label = kind;

  useEffect(() => {
    if (!open) {
      setName("");
      setDescription("");
    }
  }, [open]);

  const suggestMutation = useMutation({
    mutationFn: async () =>
      submitPendingPaperEdit({
        paper_id: paperId ? parseInt(paperId) : null,
        edit_type: KIND_EDIT_TYPE[kind],
        proposed_payload: {
          name: name.trim(),
          description: description.trim(),
        },
      }),
    onSuccess: () => {
      toast({
        title: "Suggestion submitted for review",
        description: `Thanks! An admin will review your suggested ${label} shortly.`,
      });
      onOpenChange(false);
    },
    onError: (err: unknown) => {
      const e = err as { response?: string; message?: string };
      let description = e.message || `Failed to submit your ${label} suggestion.`;
      if (e.response) {
        try {
          const parsed = JSON.parse(e.response);
          if (typeof parsed?.detail === "string") {
            description = parsed.detail;
          } else if (Array.isArray(parsed?.detail) && parsed.detail[0]?.msg) {
            description = parsed.detail[0].msg;
          }
        } catch {
          description = e.response;
        }
      }
      toast({
        title: "Could not submit suggestion",
        description,
        variant: "destructive",
      });
    },
  });

  const canSubmit = name.trim().length > 0 && description.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Suggest a new {label}</DialogTitle>
          <DialogDescription>
            Propose a {label} that isn&apos;t in the list yet. An admin will
            review your suggestion before it&apos;s added.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="suggest-name">Name</Label>
            <Input
              id="suggest-name"
              value={name}
              maxLength={NAME_MAX}
              placeholder={KIND_NAME_PLACEHOLDER[kind]}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="suggest-description">Description</Label>
            <Textarea
              id="suggest-description"
              value={description}
              maxLength={DESCRIPTION_MAX}
              placeholder={KIND_DESCRIPTION_PLACEHOLDER[kind]}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => suggestMutation.mutate()}
            disabled={suggestMutation.isPending || !canSubmit}
          >
            {suggestMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Submitting...
              </>
            ) : (
              <>
                <Check className="w-4 h-4 mr-2" />
                Submit suggestion
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default SuggestTaxonomyDialog;

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useToast } from "@/hooks/use-toast";
import type { Paper } from "@/lib/api/papers.types";
import { submissionsApi } from "@/lib/api/submissions";
import { getApiErrorMessage } from "@/lib/apiTransport";
import {
  pendingEditSubmission,
  type PendingEditOf,
  type PendingEditType,
  type PendingPaperEdit,
} from "@/lib/pendingEdits";
import { refreshPaperQueries } from "@/lib/queryInvalidation";
import { reportSubmission } from "@/lib/submissionOutcome";

/** `direct` applies immediately (admin path); `pending` submits an edit for review. */
export type SubmitMode = "direct" | "pending";

/** Props every section editor receives from `PaperDetailEditors`. */
export interface PaperSectionEditorProps {
  onOpenChange: (open: boolean) => void;
  paperId: string;
  arxivId?: string;
  submitMode?: SubmitMode;
  /** Lets the review notice acknowledge a linked author. */
  isAuthor?: boolean;
}

interface PaperSectionEditOptions<Type extends PendingEditType, Value> {
  editType: Type;
  paperId: string;
  arxivId?: string;
  submitMode: SubmitMode;
  messages: {
    /** "Thanks! An admin will review your proposed {proposal} shortly." */
    proposal: string;
    /** "Could not save {noun}" */
    noun: string;
    /** Fallback description when a direct save fails without a message. */
    failure: string;
  };
  toPendingPayload: (value: Value) => PendingEditOf<Type>["proposed_payload"];
  /** Applies the edit live; a returned paper replaces its cached copies. */
  applyDirect: (value: Value) => Promise<Paper | void>;
  /** Patches caches before a direct save and returns their rollback; the dialog closes at once. */
  applyOptimistic?: (value: Value) => Promise<() => void>;
  /** Runs once the server accepted the edit; `live` is false while it waits for review. */
  onSaved?: (value: Value, outcome: { direct: boolean; live: boolean }) => void;
  onClose: () => void;
}

/** The submit-or-apply save flow shared by the paper section editors. */
export function usePaperSectionEdit<Type extends PendingEditType, Value>({
  editType,
  paperId,
  arxivId,
  submitMode,
  messages,
  toPendingPayload,
  applyDirect,
  applyOptimistic,
  onSaved,
  onClose,
}: PaperSectionEditOptions<Type, Value>) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const pending = submitMode === "pending";

  return useMutation({
    mutationFn: async (value: Value): Promise<{ submitted: PendingPaperEdit } | { paper: Paper | void }> => pending
      ? {
          submitted: await submissionsApi.submit(
            pendingEditSubmission(Number(paperId), editType, toPendingPayload(value)),
          ),
        }
      : { paper: await applyDirect(value) },
    onMutate: async (value: Value): Promise<{ rollback?: () => void }> => {
      if (pending || !applyOptimistic) return {};
      const rollback = await applyOptimistic(value);
      onClose();
      return { rollback };
    },
    onSuccess: (result, value) => {
      if ("submitted" in result) {
        reportSubmission(result.submitted, {
          toast,
          queryClient,
          paperIds: [paperId, arxivId],
          queuedDescription: `Thanks! An admin will review your proposed ${messages.proposal} shortly.`,
        });
        onSaved?.(value, { direct: false, live: result.submitted.status === "approved" });
      } else {
        if (result.paper) refreshPaperQueries(queryClient, result.paper, [paperId, arxivId]);
        onSaved?.(value, { direct: true, live: true });
      }
      onClose();
    },
    onError: (error, _value, context) => {
      context?.rollback?.();
      toast({
        title: pending ? "Could not submit edit" : `Could not save ${messages.noun}`,
        description: getApiErrorMessage(
          error,
          pending ? "Failed to submit your edit. Please try again." : messages.failure,
        ),
        variant: "destructive",
      });
    },
  });
}

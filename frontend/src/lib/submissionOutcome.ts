import type { QueryClient } from "@tanstack/react-query";

import type { useToast } from "@/hooks/use-toast";
import type { PendingPaperEdit } from "@/lib/pendingEdits";
import { invalidatePaperDetails, invalidatePaperFeeds } from "@/lib/queryInvalidation";

interface SubmissionOutcome {
  toast: ReturnType<typeof useToast>["toast"];
  queryClient: QueryClient;
  paperIds: Array<string | null | undefined>;
  queuedDescription: string;
}

/** Tell the user whether their edit went live or was queued, and refresh the page if it did. */
export function reportSubmission(
  submitted: PendingPaperEdit,
  { toast, queryClient, paperIds, queuedDescription }: SubmissionOutcome,
): void {
  if (submitted.status === "approved") {
    invalidatePaperDetails(queryClient, paperIds);
    invalidatePaperFeeds(queryClient);
    toast({ title: "Edit applied", description: "Your change is now live on this paper." });
    return;
  }
  toast({ title: "Edit submitted for review", description: queuedDescription });
}

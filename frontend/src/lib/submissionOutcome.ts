import type { QueryClient } from "@tanstack/react-query";

import type { useToast } from "@/hooks/use-toast";
import type { PendingPaperEdit } from "@/lib/pendingEdits";
import { invalidatePaperDetails, invalidatePaperFeeds } from "@/lib/api/cacheSync";
import { isStagingEnvironment } from "@/lib/apiUrl";

/** Staging never edits the shared catalog, so a queued edit there is a test only nobody reviews. */
export const STAGING_SUBMISSION_TOAST = {
  title: "Saved on staging",
  description: "Test only: this edit stays on staging and the live catalog is unchanged.",
};

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
  if (isStagingEnvironment()) {
    toast(STAGING_SUBMISSION_TOAST);
    return;
  }
  toast({ title: "Edit submitted for review", description: queuedDescription });
}

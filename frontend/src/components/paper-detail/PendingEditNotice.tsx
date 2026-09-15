/**
 * Inline banner shown at the top of an Edit*Dialog when the signed-in user
 * cannot directly mutate the paper. Submissions land in the pending edit
 * queue for admin review.
 *
 * If the signed-in HF username matches a linked author of the paper, the
 * banner adds a short note acknowledging that — the row will still go through
 * review for now, but the API records `is_author = true` for future
 * auto-approval.
 */

interface PendingEditNoticeProps {
  isAuthor?: boolean;
}

export function PendingEditNotice({ isAuthor = false }: PendingEditNoticeProps) {
  const staging =
    typeof window !== "undefined" &&
    window.location.hostname === "staging.paperswithcode.co";
  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
      <p className="font-medium">
        {staging
          ? "Test-only: this change stays on staging."
          : "Your changes will be reviewed by an admin."}
      </p>
      <p className="mt-1 leading-snug">
        {staging
          ? "This exercises staging-local pending behavior and is not queued for production review."
          : isAuthor
          ? "We can see this paper is yours. While we're in early access an admin still reviews each edit; this will become automatic for authors soon."
          : "Submissions are queued for review and don't change the paper page until an admin approves them."}
      </p>
    </div>
  );
}

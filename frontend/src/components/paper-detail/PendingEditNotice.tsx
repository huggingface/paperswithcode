/**
 * Inline banner shown at the top of an Edit*Dialog when the signed-in user
 * cannot directly mutate the paper. Submissions land in the pending edit
 * queue for admin review.
 *
 * Most edits apply immediately and are reviewed afterwards; this notice only
 * shows where a mode still queues them. Whether an individual edit is held
 * (an unfamiliar link domain, mass removals, the daily budget) is decided by
 * the API, which reports the outcome in the submit response.
 */

interface PendingEditNoticeProps {
  isAuthor?: boolean;
}

export function PendingEditNotice(_props: PendingEditNoticeProps) {
  const staging =
    typeof window !== "undefined" &&
    window.location.hostname === "staging.paperswithcode.co";
  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
      <p className="font-medium">
        {staging
          ? "Test-only: this change stays on staging."
          : "Your changes go live right away."}
      </p>
      <p className="mt-1 leading-snug">
        {staging
          ? "This exercises staging-local pending behavior and is not queued for production review."
          : "Edits are applied immediately and reviewed afterwards. A few, such as links to unfamiliar sites, are held for an admin first."}
      </p>
    </div>
  );
}

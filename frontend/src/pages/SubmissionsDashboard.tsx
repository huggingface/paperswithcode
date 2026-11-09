import {
  evaluationChange,
  invalidatePaperDetails,
  invalidatePaperFeeds,
  refreshEvaluationQueries,
} from "@/lib/api/cacheSync";
import React from "react";
import "./SubmissionsDashboard.css";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Inbox,
  Undo2,
  Loader2,
  RefreshCw,
  XCircle,
} from "lucide-react";

import PendingEditDiff from "@/components/submissions/PendingEditDiff";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useToast } from "@/hooks/use-toast";
import { getApiErrorMessage } from "@/lib/apiTransport";
import {
  EDIT_TYPE_META,
  type PendingEditStatus,
  type PendingEditType,
  type PendingPaperEdit,
} from "@/lib/pendingEdits";
import { catalogApi } from "@/lib/api/catalog";
import { submissionsApi } from "@/lib/api/submissions";
import { cn } from "@/lib/utils";
import { submissionKeys } from "@/lib/api/queries";

const PAGE_SIZE = 25;
const STATUS_FILTERS: Array<PendingEditStatus | "all"> = ["pending", "approved", "rejected", "all"];
const EDIT_TYPE_FILTERS = ["all", ...Object.keys(EDIT_TYPE_META)] as Array<PendingEditType | "all">;

function initialsFor(username: string): string {
  return username.slice(0, 2).toUpperCase();
}

function formatLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function formatRelativeTime(value: string | null | undefined): string {
  if (!value) return "unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const diffMs = Date.now() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMinutes < 1) return "just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 14) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function statusClass(status: PendingEditStatus): string {
  if (status === "approved") return "approved";
  if (status === "rejected") return "rejected";
  return "pending";
}

function SubmissionCard({ submission }: { submission: PendingPaperEdit }) {
  const paper = submission.paper;
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const paperId = submission.paper_id;
  const isDirectorySuggestion = paperId === null;
  const isAdministrativeSuggestion = EDIT_TYPE_META[submission.edit_type].administrative;
  const directoryLabels = EDIT_TYPE_META[submission.edit_type].directory ?? {
    title: "Taxonomy directory",
    subtitle: "Directory suggestion",
  };
  const routeIdentifier = isDirectorySuggestion ? null : paper?.arxiv_id || String(paperId);
  const paperTitle = isDirectorySuggestion
    ? directoryLabels.title
    : paper?.title || `Paper #${paperId}`;
  const avatarUrl = `https://huggingface.co/${encodeURIComponent(submission.hf_username)}/avatar`;
  const isPending = submission.status === "pending";
  const showSubmitterVisibleReason =
    !!submission.user_review_reason &&
    submission.user_review_reason.trim() !== submission.admin_note?.trim();

  const invalidateAfterReview = React.useCallback(
    (reviewed: PendingPaperEdit) => {
      queryClient.invalidateQueries({ queryKey: submissionKeys.pendingEdits });
      if (reviewed.paper_id != null && reviewed.edit_type !== "evaluations") {
        invalidatePaperDetails(queryClient, [String(reviewed.paper_id), paper?.arxiv_id]);
      }
    },
    [paper?.arxiv_id, queryClient],
  );

  const approveMutation = useMutation<PendingPaperEdit, unknown, void>({
    mutationFn: () => submissionsApi.approve(submission.id),
    onSuccess: (reviewed) => {
      invalidateAfterReview(reviewed);
      if (reviewed.edit_type === "evaluations" && reviewed.paper_id != null) {
        refreshEvaluationQueries(queryClient, evaluationChange(
          String(reviewed.paper_id),
          reviewed.current_payload?.evaluations ?? [],
          reviewed.proposed_payload.operations,
          paper?.arxiv_id ?? undefined,
        ));
      } else if (reviewed.paper_id != null && !isAdministrativeSuggestion) {
        invalidatePaperFeeds(queryClient);
      }
      toast({
        title: "Submission approved",
        description: isAdministrativeSuggestion
          ? `Marked ${formatLabel(submission.edit_type)} suggestion as approved. No catalog changes were applied.`
          : `Applied ${formatLabel(submission.edit_type)} changes for ${paperTitle}.`,
      });
    },
    onError: (error) => {
      toast({
        title: "Could not approve submission",
        description: getApiErrorMessage(error, "Approval failed. Please try again."),
        variant: "destructive",
      });
    },
  });

  const rejectMutation = useMutation<PendingPaperEdit, unknown, void>({
    mutationFn: () => submissionsApi.reject(submission.id),
    onSuccess: (reviewed) => {
      invalidateAfterReview(reviewed);
      toast({
        title: "Submission rejected",
        description: `Rejected ${formatLabel(submission.edit_type)} changes for ${paperTitle}.`,
      });
    },
    onError: (error) => {
      toast({
        title: "Could not reject submission",
        description: getApiErrorMessage(error, "Rejection failed. Please try again."),
        variant: "destructive",
      });
    },
  });

  const revertMutation = useMutation<unknown, unknown, void>({
    mutationFn: () => catalogApi.rollbackEvent(submission.catalog_event_id as string),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: submissionKeys.pendingEdits });
      if (submission.paper_id != null) {
        invalidatePaperDetails(queryClient, [String(submission.paper_id), paper?.arxiv_id]);
        invalidatePaperFeeds(queryClient);
      }
      toast({ title: "Edit reverted", description: `Restored ${paperTitle} to its previous state.` });
    },
    onError: (error) => {
      toast({
        title: "Could not revert edit",
        description: getApiErrorMessage(error, "The paper changed after this edit, or it was already reverted."),
        variant: "destructive",
      });
    },
  });

  const bulkRevertMutation = useMutation<
    { reverted: number; skipped: unknown[] },
    unknown,
    boolean
  >({
    mutationFn: (suspend) =>
      submissionsApi.revertAutoApproved(submission.hf_subject as string, { suspend }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: submissionKeys.pendingEdits });
      invalidatePaperFeeds(queryClient);
      toast({
        title: `Reverted ${result.reverted} edits by @${submission.hf_username}`,
        description: result.skipped.length
          ? `${result.skipped.length} were skipped because the paper changed since.`
          : undefined,
      });
    },
    onError: (error) => {
      toast({
        title: "Could not revert edits",
        description: getApiErrorMessage(error, "Bulk revert failed. Please try again."),
        variant: "destructive",
      });
    },
  });

  const confirmBulkRevert = (suspend: boolean) => {
    const message = `Revert every edit @${submission.hf_username} had auto-applied in the last 7 days${suspend ? " and suspend the account" : ""}?`;
    if (window.confirm(message)) bulkRevertMutation.mutate(suspend);
  };

  const isAutoApplied = submission.reviewed_by_kind === "auto";
  const canRevert = isAutoApplied && !!submission.catalog_event_id;
  const isApproving = approveMutation.isPending;
  const isRejecting = rejectMutation.isPending;
  const isMutating = isApproving || isRejecting;
  const isReverting = revertMutation.isPending || bulkRevertMutation.isPending;

  return (
    <article id={`submission-${submission.id}`} className="submission-card">
      <header className="submission-card-header">
        <div className="submission-card-top">
          <div>
            {routeIdentifier ? (
              <a
                href={`/paper/${encodeURIComponent(routeIdentifier)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="submission-title"
              >
                {paperTitle}
              </a>
            ) : (
              <div className="submission-title">{paperTitle}</div>
            )}
            <div className="submission-meta">
              <span>#{submission.id}</span>
              <span>
                {isDirectorySuggestion
                  ? directoryLabels.subtitle
                  : `Paper #${submission.paper_id}`}
              </span>
              <span>{formatRelativeTime(submission.created_at)}</span>
            </div>
          </div>
          <div className="submission-badges">
            <span className="submission-pill">{formatLabel(submission.edit_type)}</span>
            {isAutoApplied && <span className="submission-pill">Auto-applied</span>}
            {submission.is_author && (
              <span className="submission-pill author">Linked author</span>
            )}
            <span className={cn("submission-pill status", statusClass(submission.status))}>
              {submission.status}
            </span>
          </div>
        </div>

        <a
          href={`https://huggingface.co/${encodeURIComponent(submission.hf_username)}`}
          target="_blank"
          rel="noopener noreferrer"
          className="submission-user"
        >
          <Avatar className="h-6 w-6">
            <AvatarImage src={avatarUrl} alt={submission.hf_username} />
            <AvatarFallback className="text-[10px]">{initialsFor(submission.hf_username)}</AvatarFallback>
          </Avatar>
          <span>@{submission.hf_username}</span>
        </a>
      </header>

      <div className="submission-diff">
        <PendingEditDiff
          edit={submission}
        />
      </div>

      {submission.conflict_payload && (
        <div className="submission-empty submission-empty-warn">
          Canonical state changed after this submission. Review the conflict before deciding.
          <pre>{JSON.stringify(submission.conflict_payload, null, 2)}</pre>
        </div>
      )}
      <footer className="submission-actions">
        {isPending ? (
          <>
            <div className="submission-action-buttons">
              <button
                type="button"
                onClick={() => rejectMutation.mutate()}
                disabled={isMutating}
                className="submission-action-btn reject"
              >
                {isRejecting ? <Loader2 className="spin" size={14} /> : <XCircle size={14} />}
                Reject
              </button>
              <button
                type="button"
                onClick={() => approveMutation.mutate()}
                disabled={isMutating}
                className="submission-action-btn approve"
              >
                {isApproving ? <Loader2 className="spin" size={14} /> : <CheckCircle2 size={14} />}
                Approve
              </button>
            </div>
          </>
        ) : (
          <div className="submission-reviewed">
            <span>
              Reviewed by <strong>{submission.reviewed_by || "unknown"}</strong>
              {submission.reviewed_at ? ` ${formatRelativeTime(submission.reviewed_at)}` : ""}
            </span>
            {submission.admin_note && (
              <span>
                Admin note: <strong>{submission.admin_note}</strong>
              </span>
            )}
            {showSubmitterVisibleReason && (
              <span>Submitter-visible reason: <strong>{submission.user_review_reason}</strong></span>
            )}
            {canRevert && (
              <div className="submission-action-buttons">
                <button
                  type="button"
                  onClick={() => revertMutation.mutate()}
                  disabled={isReverting}
                  className="submission-action-btn reject"
                >
                  {revertMutation.isPending ? <Loader2 className="spin" size={14} /> : <Undo2 size={14} />}
                  Revert this edit
                </button>
                {submission.hf_subject && (
                  <>
                    <button
                      type="button"
                      onClick={() => confirmBulkRevert(false)}
                      disabled={isReverting}
                      className="submission-action-btn reject"
                    >
                      Revert all by @{submission.hf_username}
                    </button>
                    <button
                      type="button"
                      onClick={() => confirmBulkRevert(true)}
                      disabled={isReverting}
                      className="submission-action-btn reject"
                    >
                      Revert all and suspend
                    </button>
                  </>
                )}
              </div>
            )}
            {submission.applied_payload && (
              <details>
                <summary>
                  {isAdministrativeSuggestion ? "Reviewed payload" : "Applied payload"}
                </summary>
                <pre>{JSON.stringify(submission.applied_payload, null, 2)}</pre>
              </details>
            )}
            {submission.result_entity_type && (
              <span>
                Created/applied: <strong>{submission.result_entity_type} #{submission.result_entity_id}</strong>
              </span>
            )}
          </div>
        )}
      </footer>
    </article>
  );
}

export default function SubmissionsDashboard() {
  const { toast } = useToast();
  const [status, setStatus] = React.useState<PendingEditStatus | "all">("pending");
  const [editType, setEditType] = React.useState<PendingEditType | "all">("all");
  const [autoOnly, setAutoOnly] = React.useState(false);

  const filters = {
    edit_type: editType === "all" ? undefined : editType,
    reviewed_by_kind: autoOnly ? ("auto" as const) : undefined,
  };
  // Counts ignore the status tab, so switching tabs reuses them.
  const countsQuery = useQuery({
    queryKey: submissionKeys.counts(editType, autoOnly),
    queryFn: async () => (await submissionsApi.list({ ...filters, status: "all", limit: 1 })).status_counts,
    staleTime: 30 * 1000,
  });

  const listQuery = useInfiniteQuery({
    queryKey: submissionKeys.list({ status, editType, autoOnly }),
    queryFn: ({ pageParam }) => submissionsApi.list({ ...filters, status, limit: PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (page, pages) => {
      const loaded = pages.reduce((sum, { results }) => sum + results.length, 0);
      return page.results.length > 0 && loaded < page.count ? loaded : undefined;
    },
    retry: false,
  });
  const submissions = React.useMemo(
    () => listQuery.data?.pages.flatMap((page) => page.results) ?? [],
    [listQuery.data],
  );

  React.useEffect(() => {
    if (!listQuery.error) return;
    toast({
      title: "Could not load submissions",
      description: getApiErrorMessage(listQuery.error, "Failed to load pending paper edits."),
      variant: "destructive",
    });
  }, [listQuery.error, toast]);

  const counts = countsQuery.data;
  const allCount = counts ? counts.pending + counts.approved + counts.rejected : undefined;
  const statusCounts: Record<PendingEditStatus | "all", number | undefined> = {
    pending: counts?.pending,
    approved: counts?.approved,
    rejected: counts?.rejected,
    all: allCount,
  };
  const totalCount = listQuery.data?.pages[0]?.count ?? 0;

  return (
    <div className="page submissions-page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            Pending <em>Edits</em>
          </h1>
          <div className="feed-subtitle">
            Review submitted changes to paper metadata and benchmark results
          </div>
        </div>
        <button
          type="button"
          className="feedback-link"
          onClick={() => {
            countsQuery.refetch();
            listQuery.refetch();
          }}
          disabled={listQuery.isFetching || countsQuery.isFetching}
        >
          <RefreshCw className={cn((listQuery.isFetching || countsQuery.isFetching) && "spin")} size={14} />
          Refresh
        </button>
      </div>

      <div className="submissions-filter-panel">
        <div className="submission-filter-block">
          <div className="sidebar-label">Status</div>
          <div className="period-switch">
            {STATUS_FILTERS.map((item) => (
              <button
                key={item}
                type="button"
                className={cn("period-btn", status === item && "active")}
                onClick={() => setStatus(item)}
              >
                {item}
                {statusCounts[item] != null && <span className="submission-count">{statusCounts[item]}</span>}
              </button>
            ))}
            <button
              type="button"
              className={cn("period-btn", autoOnly && "active")}
              onClick={() => {
                setAutoOnly((value) => !value);
                if (!autoOnly) setStatus("approved");
              }}
            >
              auto-applied only
            </button>
          </div>
        </div>
        <div className="submission-filter-block">
          <div className="sidebar-label">Edit Type</div>
          <div className="sort-options submissions-type-options">
            {EDIT_TYPE_FILTERS.map((item) => (
              <button
                key={item}
                type="button"
                className={cn("sort-btn", editType === item && "active")}
                onClick={() => setEditType(item)}
              >
                {item === "all" ? "all" : EDIT_TYPE_META[item].label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div>
        <div className="sort-bar submissions-sort-bar">
          <div>
            <div className="sort-options">
              <span className="results-count">
                {listQuery.isFetching ? "refreshing" : `${totalCount} submissions`}
              </span>
            </div>
          </div>
        </div>
        {listQuery.isLoading ? (
          <div className="submission-loading">
            <Loader2 className="spin" size={18} />
            <span>Loading submissions...</span>
          </div>
        ) : listQuery.isError ? (
          <div className="submission-empty submission-empty-warn" role="alert">
            <Inbox size={28} />
            <h2>Could not display submissions.</h2>
            <p>{getApiErrorMessage(listQuery.error, "The submissions response was invalid.")}</p>
          </div>
        ) : submissions.length === 0 ? (
          <div className="submission-empty">
            <Inbox size={28} />
            <h2>No pending submissions.</h2>
            <p>
              The SQL and curl fallback is still documented in{" "}
              <a
                href="https://github.com/huggingface/paperswithcode/blob/main/docs/operations.md"
                target="_blank"
                rel="noopener noreferrer"
              >
                operations.md
              </a>
              .
            </p>
          </div>
        ) : (
          <div className="submission-list">
            {submissions.map((submission) => (
              <SubmissionCard key={submission.id} submission={submission} />
            ))}
          </div>
        )}

        {submissions.length > 0 && (
          <div className="submission-pagination">
            <p>
              Showing {submissions.length} of {totalCount} submissions
            </p>
            {listQuery.hasNextPage && (
              <button
                type="button"
                className="feedback-link"
                onClick={() => listQuery.fetchNextPage()}
                disabled={listQuery.isFetching}
              >
                {listQuery.isFetchingNextPage && <Loader2 className="spin" size={14} />}
                Load more
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

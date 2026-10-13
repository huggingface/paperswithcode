import { evaluationChange, refreshEvaluationQueries } from "@/lib/evaluationQueryInvalidation";
import { paperQueryKeys } from "@/lib/paperQueryKeys";
import { invalidatePaperDetails, invalidatePaperFeeds } from "@/lib/queryInvalidation";
import React from "react";
import "./SubmissionsDashboard.css";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Inbox,
  Loader2,
  RefreshCw,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import PendingEditDiff from "@/components/submissions/PendingEditDiff";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/lib/authContext";
import {
  type PendingEditStatus,
  type PendingEditType,
  type PendingPaperEdit,
} from "@/lib/pendingEdits";
import { papersApi } from "@/lib/api/papers";
import type { Paper } from "@/lib/api/papers.types";
import { submissionsApi } from "@/lib/api/submissions";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 25;
const STATUS_FILTERS: Array<PendingEditStatus | "all"> = ["pending", "approved", "rejected", "all"];
const EDIT_TYPE_FILTERS: Array<PendingEditType | "all"> = [
  "all",
  "tasks",
  "methods",
  "evaluations",
  "repositories",
  "project_pages",
  "source_url",
  "x_threads",
  "new_task",
  "new_method",
  "new_benchmark",
  "new_metric",
  "new_conference",
  "new_organization",
  "new_external_paper",
];
const COUNT_STATUSES: PendingEditStatus[] = ["pending", "approved", "rejected"];
const ADMINISTRATIVE_SUGGESTION_TYPES = new Set<PendingEditType>([
  "new_task",
  "new_method",
  "new_benchmark",
  "new_metric",
  "new_conference",
]);

interface ListData {
  count: number;
  results: PendingPaperEdit[];
}

function initialsFor(username: string): string {
  return username.slice(0, 2).toUpperCase();
}

function formatLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function formatEditTypeFilterLabel(value: PendingEditType | "all"): string {
  return value === "new_external_paper" ? "external paper" : formatLabel(value);
}

const DIRECTORY_SUGGESTION_LABELS: Partial<
  Record<PendingEditType, { title: string; subtitle: string }>
> = {
  new_task: { title: "New task", subtitle: "Task suggestion" },
  new_method: { title: "New method", subtitle: "Method suggestion" },
  new_benchmark: { title: "New benchmark", subtitle: "Benchmark suggestion" },
  new_metric: { title: "New metric", subtitle: "Metric suggestion" },
  new_conference: { title: "New conference", subtitle: "Conference suggestion" },
  new_organization: { title: "New organization", subtitle: "Organization suggestion" },
  new_external_paper: { title: "External paper", subtitle: "External paper submission" },
};

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

function errorDescription(error: unknown, fallback: string): string {
  const err = error as { response?: string; message?: string };
  if (err.response) {
    try {
      const parsed = JSON.parse(err.response);
      if (typeof parsed?.detail === "string") return parsed.detail;
      if (Array.isArray(parsed?.detail) && parsed.detail[0]?.msg) return parsed.detail[0].msg;
    } catch {
      return err.response;
    }
  }
  return err.message || fallback;
}

function statusClass(status: PendingEditStatus): string {
  if (status === "approved") return "approved";
  if (status === "rejected") return "rejected";
  return "pending";
}

function paperRouteIdentifier(paper: Paper | undefined, fallbackId: number): string {
  return paper?.arxiv_id || paper?.id || String(fallbackId);
}

function sortByCreatedDesc(rows: PendingPaperEdit[]): PendingPaperEdit[] {
  return [...rows].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
}

async function fetchSubmissions(
  status: PendingEditStatus | "all",
  editType: PendingEditType | "all",
  visibleLimit: number,
): Promise<ListData> {
  const edit_type = editType === "all" ? undefined : editType;
  if (status !== "all") {
    return submissionsApi.list({
      status,
      edit_type,
      limit: visibleLimit,
      offset: 0,
    });
  }

  const pages = await Promise.all(
    COUNT_STATUSES.map((itemStatus) =>
      submissionsApi.list({
        status: itemStatus,
        edit_type,
        limit: visibleLimit,
        offset: 0,
      }),
    ),
  );

  return {
    count: pages.reduce((sum, page) => sum + page.count, 0),
    results: sortByCreatedDesc(pages.flatMap((page) => page.results)).slice(0, visibleLimit),
  };
}

function AdminPlaceholder() {
  return (
    <div className="page">
      <div className="submission-empty submission-empty-warn">
        <ShieldAlert size={22} />
        <h1>Admin access required</h1>
        <p>Sign in with an allowlisted Hugging Face admin account to review paper edit submissions.</p>
      </div>
    </div>
  );
}

function LoadingPlaceholder() {
  return (
    <div className="page">
      <div className="submission-loading">
        <Loader2 className="spin" size={18} />
        <span>Checking admin session...</span>
      </div>
    </div>
  );
}

function SubmissionCard({
  submission,
  paper,
}: {
  submission: PendingPaperEdit;
  paper?: Paper;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const paperId = submission.paper_id;
  const isDirectorySuggestion = paperId === null;
  const isAdministrativeSuggestion = ADMINISTRATIVE_SUGGESTION_TYPES.has(
    submission.edit_type,
  );
  const directoryLabels = DIRECTORY_SUGGESTION_LABELS[submission.edit_type] ?? {
    title: "Taxonomy directory",
    subtitle: "Directory suggestion",
  };
  const routeIdentifier = isDirectorySuggestion
    ? null
    : paperRouteIdentifier(paper, paperId);
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
      queryClient.invalidateQueries({ queryKey: ["pendingPaperEdits"] });
      queryClient.invalidateQueries({ queryKey: ["pendingPaperEdit", reviewed.id] });
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
          reviewed.proposed_payload.operations.map(operation => operation.op === "create"
            ? { kind: "create", data: operation.data }
            : operation.op === "update"
              ? { kind: "update", evaluationId: operation.evaluation_id, data: operation.data }
              : { kind: "delete", evaluationId: operation.evaluation_id }),
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
        description: errorDescription(error, "Approval failed. Please try again."),
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
        description: errorDescription(error, "Rejection failed. Please try again."),
        variant: "destructive",
      });
    },
  });

  const isApproving = approveMutation.isPending;
  const isRejecting = rejectMutation.isPending;
  const isMutating = isApproving || isRejecting;

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
  const { user, isLoading: authLoading } = useAuth();
  const { toast } = useToast();
  const [status, setStatus] = React.useState<PendingEditStatus | "all">("pending");
  const [editType, setEditType] = React.useState<PendingEditType | "all">("all");
  const [visibleLimit, setVisibleLimit] = React.useState(PAGE_SIZE);
  const isAdmin = !!user?.is_admin;

  React.useEffect(() => {
    setVisibleLimit(PAGE_SIZE);
  }, [status, editType]);

  const countsQuery = useQuery({
    queryKey: ["pendingPaperEdits", "counts", editType],
    queryFn: async () => {
      const edit_type = editType === "all" ? undefined : editType;
      const pages = await Promise.all(
        COUNT_STATUSES.map((itemStatus) =>
          submissionsApi.list({
            status: itemStatus,
            edit_type,
            limit: 1,
            offset: 0,
          }),
        ),
      );
      return Object.fromEntries(
        pages.map((page, index) => [COUNT_STATUSES[index], page.count]),
      ) as Record<PendingEditStatus, number>;
    },
    enabled: isAdmin,
    staleTime: 30 * 1000,
  });

  const listQuery = useQuery({
    queryKey: ["pendingPaperEdits", { status, editType, visibleLimit }],
    queryFn: () => fetchSubmissions(status, editType, visibleLimit),
    enabled: isAdmin,
    retry: false,
  });

  const paperIds = React.useMemo(
    () =>
      Array.from(
        new Set(
          (listQuery.data?.results ?? [])
            .map((row) => row.paper_id)
            .filter((paperId): paperId is number => paperId != null),
        ),
      ).sort((a, b) => a - b),
    [listQuery.data?.results],
  );

  const paperQueries = useQueries({
    queries: paperIds.map((paperId) => ({
      queryKey: paperQueryKeys.summary(String(paperId)),
      queryFn: () => papersApi.get(String(paperId), false),
      enabled: isAdmin,
      staleTime: 5 * 60 * 1000,
    })),
  });

  const papersById = React.useMemo(() => {
    const map = new Map<number, Paper>();
    paperQueries.forEach((query) => {
      const paper = query.data;
      if (!paper) return;
      const id = Number(paper.id);
      if (Number.isFinite(id)) map.set(id, paper);
    });
    return map;
  }, [paperQueries]);

  React.useEffect(() => {
    if (!listQuery.error) return;
    toast({
      title: "Could not load submissions",
      description: errorDescription(listQuery.error, "Failed to load pending paper edits."),
      variant: "destructive",
    });
  }, [listQuery.error, toast]);

  if (authLoading) return <LoadingPlaceholder />;
  if (!isAdmin) return <AdminPlaceholder />;

  const counts = countsQuery.data;
  const allCount = counts ? counts.pending + counts.approved + counts.rejected : undefined;
  const statusCounts: Record<PendingEditStatus | "all", number | undefined> = {
    pending: counts?.pending,
    approved: counts?.approved,
    rejected: counts?.rejected,
    all: allCount,
  };
  const submissions = listQuery.data?.results ?? [];
  const totalCount = listQuery.data?.count ?? 0;
  const hasMore = submissions.length < totalCount;

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
                {formatEditTypeFilterLabel(item)}
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
            <p>{errorDescription(listQuery.error, "The submissions response was invalid.")}</p>
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
              <SubmissionCard
                key={submission.id}
                submission={submission}
                paper={
                  submission.paper_id == null
                    ? undefined
                    : papersById.get(submission.paper_id)
                }
              />
            ))}
          </div>
        )}

        {submissions.length > 0 && (
          <div className="submission-pagination">
            <p>
              Showing {submissions.length} of {totalCount} submissions
            </p>
            {hasMore && (
              <button
                type="button"
                className="feedback-link"
                onClick={() => setVisibleLimit((value) => value + PAGE_SIZE)}
                disabled={listQuery.isFetching}
              >
                {listQuery.isFetching && <Loader2 className="spin" size={14} />}
                Load more
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

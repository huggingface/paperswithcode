import { EyeOff } from "lucide-react";
import { Link } from "react-router-dom";

import { Icon } from "@/components/Icon";
import ClosedSourceEvalBadge from "@/components/ClosedSourceEvalBadge";
import ExternalSourceEvalBadge from "@/components/ExternalSourceEvalBadge";
import { Skeleton } from "@/components/ui/skeleton";
import { resultsTaskAnchorId, resultsTaskHash } from "@/hooks/usePaperDetailPageModel";
import type { Evaluation } from "@/lib/api/evaluations.types";
import type { Paper } from "@/lib/api/papers.types";
import { isCodexAddEvalsEnabled } from "@/lib/apiUrl";
import { formatMetricValue } from "@/lib/utils";

import { CodexPaperJobDialog } from "./CodexPaperJobDialog";
import { PaperSectionRule } from "./PaperSectionRule";

export interface EvaluationTaskGroup {
  taskId: string;
  taskName: string;
  taskSlug?: string;
  rows: Evaluation[];
}

export const CLOSED_SOURCE_SETTING_HREF = "/settings#closed-source-evals";

function HiddenClosedSourceEvalsNotice({
  count,
  everyResultHidden,
  onShow,
}: {
  count: number;
  everyResultHidden: boolean;
  onShow: () => void;
}) {
  const results = count === 1 ? "result" : "results";
  return (
    <div className="hidden-evals-notice" role="note">
      <EyeOff className="hidden-evals-notice-icon" aria-hidden="true" />
      <div className="hidden-evals-notice-body">
        <p className="hidden-evals-notice-title">
          {everyResultHidden
            ? `No evals shown for this paper: all ${count} ${results} are from closed-source models.`
            : `${count} closed-source ${results} hidden.`}
        </p>
        <p className="hidden-evals-notice-desc">
          You turned on <strong>Hide closed-source models</strong> in your settings.
          Turn it off to see closed-source results here and on every leaderboard.
        </p>
        <div className="hidden-evals-notice-actions">
          <button type="button" className="hidden-evals-notice-show" onClick={onShow}>
            Show closed-source results
          </button>
          <Link to={CLOSED_SOURCE_SETTING_HREF} className="hidden-evals-notice-link">
            Change in Settings →
          </Link>
        </div>
      </div>
    </div>
  );
}

export function PaperResultsSection({
  canCopyBadge,
  canEdit,
  evaluationsByTask,
  evaluationsLoading,
  hiddenClosedSourceCount,
  isAdmin,
  onCopyBadge,
  onEdit,
  onRefresh,
  onShowClosedSourceEvals,
  paper,
  visibleEvaluationCount,
}: {
  canCopyBadge: boolean;
  canEdit: boolean;
  evaluationsByTask: EvaluationTaskGroup[];
  evaluationsLoading: boolean;
  hiddenClosedSourceCount: number;
  isAdmin: boolean;
  onCopyBadge: () => void;
  onEdit: () => void;
  onRefresh: () => void;
  onShowClosedSourceEvals: () => void;
  paper: Paper;
  visibleEvaluationCount: number;
}) {
  return (
    <>
      <PaperSectionRule
        id="results"
        label="Results"
        accent={
          <span className="accent">
            {visibleEvaluationCount} benchmarks
            {canCopyBadge && (
              <button
                type="button"
                className="edit-link results-badge-copy"
                onClick={onCopyBadge}
                title="Copy live leaderboard badges for your repository README"
              >
                <Icon name="copy" size={10} /> Copy PwC badge
              </button>
            )}
            {isAdmin && isCodexAddEvalsEnabled() && (
              <CodexPaperJobDialog
                kind="add-evals"
                triggerClassName="edit-link"
                paperId={Number(paper.id)}
                paperTitle={paper.title}
                onComplete={onRefresh}
              />
            )}
            {canEdit && (
              <button type="button" onClick={onEdit} className="edit-link">
                edit
              </button>
            )}
          </span>
        }
      />
      {!evaluationsLoading && hiddenClosedSourceCount > 0 && (
        <HiddenClosedSourceEvalsNotice
          count={hiddenClosedSourceCount}
          everyResultHidden={evaluationsByTask.length === 0}
          onShow={onShowClosedSourceEvals}
        />
      )}
      {evaluationsLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : evaluationsByTask.length > 0 ? (
        evaluationsByTask.map((group) => (
          <div
            key={group.taskId}
            className={group.taskSlug ? "paper-section-anchor" : undefined}
            id={group.taskSlug ? resultsTaskAnchorId(group.taskSlug) : undefined}
          >
            <div className="section-rule">
              <span>
                {group.taskSlug ? (
                  <>
                    <Link to={`/tasks/${group.taskSlug}`}>{group.taskName}</Link>
                    <a
                      href={resultsTaskHash(group.taskSlug)}
                      className="section-anchor-link results-task-permalink"
                      aria-label={`Permalink to ${group.taskName} results on this paper`}
                      title="Link to this task's results"
                    >
                      #
                    </a>
                  </>
                ) : group.taskName}
              </span>
              <span className="accent">
                {group.rows.length} {group.rows.length === 1 ? "result" : "results"}
              </span>
            </div>
            <table className="results-table">
              <colgroup>
                <col style={{ width: "28%" }} />
                <col style={{ width: "28%" }} />
                <col style={{ width: "14%" }} />
                <col style={{ width: "12%" }} />
                <col style={{ width: "8%" }} />
                <col style={{ width: "10%" }} />
              </colgroup>
              <thead>
                <tr>
                  <th>Benchmark</th><th>Model</th><th>Metric</th><th>Value</th><th>Rank</th><th>Compare</th>
                </tr>
              </thead>
              <tbody>
                {group.rows.map((evaluation) => (
                  <tr key={evaluation.id}>
                    <td className="benchmark">
                      {evaluation.dataset_slug ? (
                        <Link to={`/benchmark/${evaluation.dataset_slug}`}>
                          {evaluation.dataset_name || "—"}
                        </Link>
                      ) : evaluation.dataset_name || "—"}
                    </td>
                    <td className="model" title={evaluation.model_name || undefined}>
                      {evaluation.hf_model_url ? (
                        <a
                          href={evaluation.hf_model_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="model-hf-link"
                          title={`Open ${evaluation.model_name || "model"} on Hugging Face`}
                        >
                          {evaluation.model_name || "—"}
                        </a>
                      ) : evaluation.model_name || "—"}
                      {evaluation.is_open === false && <ClosedSourceEvalBadge />}
                      {(evaluation.external ?? evaluation.is_external) && (
                        <ExternalSourceEvalBadge
                          sourceUrl={evaluation.source_url || evaluation.external_source_url || evaluation.result_url}
                        />
                      )}
                    </td>
                    <td className="metric">{evaluation.best_metric}</td>
                    <td className="value">
                      {formatMetricValue(evaluation.metrics?.[evaluation.best_metric || ""])}
                    </td>
                    <td className="rank">
                      {evaluation.best_rank != null ? `#${evaluation.best_rank}` : "—"}
                    </td>
                    <td className="compare">
                      {evaluation.dataset_slug && (
                        <Link to={`/benchmark/${evaluation.dataset_slug}?${[
                          evaluation.task_slug ? `task=${encodeURIComponent(evaluation.task_slug)}` : "",
                          `eval=${encodeURIComponent(evaluation.id)}`,
                        ].filter(Boolean).join("&")}`}>
                          Compare →
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))
      ) : hiddenClosedSourceCount > 0 ? null : (
        <p style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-faint)" }}>
          No benchmark results recorded yet.
        </p>
      )}
    </>
  );
}

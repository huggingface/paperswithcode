import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Database,
  ExternalLink,
  FileText,
  Images,
  Loader2,
  ShieldAlert,
  TrendingUp,
  XCircle,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { StatusBadge } from "@/components/cron/StatusBadge";
import { Badge } from "@/components/ui/badge";
import {
  operationsApi,
  type CronHealthAxis,
  type CronJobHealth,
  type CronJobStatus,
  type CronWorkflowStatus,
  type PaperMarkdownJobsResponse,
  type PaperMarkdownBudget,
  type PaperMarkdownRemoteJob,
  type PaperMarkdownJobProfile,
} from "@/lib/api/operations";
import { formatCronDate, formatUsd, toneClass, type Tone } from "@/lib/cronStatus";
import { adminQueryKeys } from "@/lib/api/queryKeys";

function formatDuration(duration: number | null): string {
  if (duration == null) return "N/A";
  if (duration < 60) return `${duration.toFixed(1)}s`;
  if (duration < 3600) return `${(duration / 60).toFixed(1)}m`;
  return `${(duration / 3600).toFixed(1)}h`;
}

function formatWorkflowStatus(workflow: CronWorkflowStatus): string {
  if (!workflow.available) return "Unavailable";
  if (workflow.status === "completed") return workflow.conclusion ?? "completed";
  return workflow.status ?? "unknown";
}

function metricLabel(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function PaperMarkdownBudgetCard({
  title,
  budget,
  profile,
}: {
  title: string;
  budget: PaperMarkdownBudget;
  profile?: PaperMarkdownJobProfile;
}) {
  const unmetered = budget.cost_policy === "unmetered_hf" || budget.budget_enforced === false;
  const percent = Math.min(100, budget.current_exposure_usd / budget.ceiling_usd * 100);
  const planLabel = unmetered
    ? "Unmetered HF"
    : budget.affordable_jobs === 0 && budget.desired_jobs > 0
    ? "No shard fits"
    : budget.affordable_jobs < budget.desired_jobs
      ? `${budget.affordable_jobs} of ${budget.desired_jobs} planned shards fit`
      : `${budget.affordable_jobs} planned ${budget.affordable_jobs === 1 ? "shard fits" : "shards fit"}`;
  return (
    <div className={`cron-metric-card space-y-3 ${budget.can_launch_planned ? "" : "cron-status--broken"}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold">{title}</div>
          <div className="text-xs cron-muted">
            {budget.window === "rolling_30_days" ? "Rolling 30-day window" : "All history · no automatic reset"}
          </div>
        </div>
        <StatusBadge tone={budget.can_launch_planned ? "healthy" : "broken"}>
          {planLabel}
        </StatusBadge>
      </div>
      {!unmetered && (
        <div role="progressbar" aria-label={`${title} current budget exposure`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)} className="h-2 rounded bg-muted">
          <div className="h-2 rounded bg-primary" style={{ width: `${percent}%` }} />
        </div>
      )}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
        <div><span className="cron-label">Completed-job estimate</span><div>{formatUsd(budget.spent_usd)}</div></div>
        <div><span className="cron-label">Active reservations</span><div>{formatUsd(budget.active_reserved_usd)}</div></div>
        <div><span className="cron-label">Current exposure</span><div>{formatUsd(budget.current_exposure_usd)}</div></div>
        <div><span className="cron-label">Admission policy</span><div>{unmetered ? "HF-owned · no monetary gate" : `${formatUsd(budget.ceiling_usd)} cap · ${formatUsd(budget.headroom_usd)} headroom`}</div></div>
        <div><span className="cron-label">Affordable plan reserves</span><div>{formatUsd(budget.planned_reserved_usd)}</div></div>
        <div><span className="cron-label">Projected exposure</span><div>{formatUsd(budget.projected_usd)}</div></div>
        <div><span className="cron-label">Rate assumption</span><div>{formatUsd(budget.hourly_rate_usd)}/hour · {budget.reservation_hours_per_job}h</div></div>
        <div><span className="cron-label">Next admission</span><div>{unmetered ? "Now, subject to capacity" : budget.next_admission_at ? formatCronDate(budget.next_admission_at) : budget.affordable_jobs > 0 ? "Now" : "No scheduled admission"}</div></div>
        <div><span className="cron-label">Unknown terminal reserve</span><div>{formatUsd(budget.unknown_terminal_reservation_usd ?? 0)} · {(budget.unknown_terminal_reservation_count ?? 0).toLocaleString()} jobs</div></div>
      </div>
      {profile && (
        <div className="text-xs cron-muted">
          Profile <strong>{profile.profile_id}</strong> · max {profile.max_papers.toLocaleString()} papers · hard {formatDuration(profile.hard_timeout_seconds)} · soft {formatDuration(profile.soft_deadline_seconds)}
        </div>
      )}
      <p className="text-xs cron-muted">
        {unmetered
          ? "HF owns this workload, so monetary admission is disabled; concurrency and timeout limits still apply. Runtime cost remains an operational estimate."
          : "Projected exposure is an admission-control estimate, not a provider invoice. Each launch reserves the full timeout until actual runtime is known."}
      </p>
    </div>
  );
}

const statusIcon = {
  healthy: CheckCircle2,
  degraded: AlertTriangle,
  broken: XCircle,
  running: Loader2,
  stuck: XCircle,
  unknown: AlertCircle,
} satisfies Record<CronJobHealth, typeof Activity>;

function Status({ status, isRunning }: { status: CronJobHealth; isRunning: boolean }) {
  const effectiveStatus = isRunning ? "running" : status;
  const StatusIcon = statusIcon[effectiveStatus];
  return (
    <StatusIcon
      className={`cron-status-icon ${toneClass(effectiveStatus)}${effectiveStatus === "running" ? " animate-spin" : ""}`}
    />
  );
}

function AxisBadge({ label, axis }: { label: string; axis: CronHealthAxis }) {
  return (
    <StatusBadge tone={axis.status} title={axis.reason}>
      {label}: {axis.status}
    </StatusBadge>
  );
}

function MetricGroup({
  icon: Icon,
  title,
  metrics,
}: {
  icon: typeof Activity;
  title: string;
  metrics: Record<string, string | number>;
}) {
  return (
    <div>
      <div className="cron-section-heading">
        <Icon className="h-4 w-4" />
        <h4>{title}</h4>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {Object.entries(metrics).map(([key, value]) => (
          <div key={key} className="cron-metric-card">
            <div className="cron-label">{metricLabel(key)}</div>
            <div className="text-lg font-semibold">
              {typeof value === "number" ? value.toLocaleString() : value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function WorkflowDetails({ workflow }: { workflow: CronWorkflowStatus }) {
  return (
    <div>
      <div className="cron-section-heading">
        <Activity className="h-4 w-4" />
        <h4>GitHub Actions</h4>
      </div>
      <div className="cron-metric-card space-y-2 text-sm">
        {[
          ["Workflow", workflow.workflow_file],
          ["Run", workflow.run_id ?? "N/A"],
          ["Status", formatWorkflowStatus(workflow)],
          ...(workflow.updated_at ? [["Updated", formatCronDate(workflow.updated_at)]] : []),
        ].map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-3">
            <span className="cron-label">{label}</span>
            <span className={label === "Workflow" ? "font-mono text-xs" : undefined}>{value}</span>
          </div>
        ))}
        {workflow.failed_jobs && workflow.failed_jobs.length > 0 && (
          <div>
            <div className="cron-label mb-1">Failed jobs</div>
            <div className="flex gap-2 flex-wrap">
              {workflow.failed_jobs.map((jobName) => (
                <StatusBadge key={jobName} tone="broken">{jobName}</StatusBadge>
              ))}
            </div>
          </div>
        )}
        {workflow.job_conclusions && Object.keys(workflow.job_conclusions).length > 0 && (
          <div>
            <div className="cron-label mb-1">Job conclusions</div>
            <div className="flex gap-2 flex-wrap">
              {Object.entries(workflow.job_conclusions).map(([jobName, conclusion]) => (
                <Badge key={jobName} variant="outline">{jobName}: {conclusion ?? "running"}</Badge>
              ))}
            </div>
          </div>
        )}
        {(workflow.error || workflow.view_error) && (
          <div className="cron-message cron-message--error">{workflow.error ?? workflow.view_error}</div>
        )}
      </div>
    </div>
  );
}

const remoteStageTones: Record<string, Tone> = {
  COMPLETED: "healthy",
  ERROR: "broken",
  CANCELED: "broken",
  RUNNING: "running",
};

const outcomeTones: Record<string, Tone> = {
  success: "healthy",
  partial: "degraded",
  interrupted: "degraded",
  infrastructure_failure: "broken",
  worker_failure: "broken",
  active: "running",
};

function PaperMarkdownShard({ job }: { job: PaperMarkdownRemoteJob }) {
  const progress = job.progress;
  const omittedImages = progress?.omitted_images ?? 0;
  const percentage = progress?.total_papers
    ? Math.min(100, (progress.processed_papers / progress.total_papers) * 100)
    : 0;
  return (
    <div className="cron-metric-card space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold">
            {job.mode ?? "unknown"} · shard {job.shard_id ?? "N/A"} · attempt {job.provider_attempt ?? 1}
          </div>
          <div className="font-mono text-xs cron-muted truncate">{job.id}</div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge tone={remoteStageTones[job.stage] ?? "unknown"}>
            {job.stage.toLowerCase()}
          </StatusBadge>
          {job.effective_outcome && (
            <StatusBadge tone={outcomeTones[job.effective_outcome] ?? "unknown"}>
              output: {job.effective_outcome.replace(/_/g, " ")}
            </StatusBadge>
          )}
          {job.failure_cause && (
            <StatusBadge tone={outcomeTones[job.effective_outcome ?? ""] ?? "unknown"}>
              cause: {job.failure_cause.replace(/_/g, " ")}
            </StatusBadge>
          )}
          {job.url && (
            <a
              href={job.url}
              target="_blank"
              rel="noreferrer"
              aria-label={`Open Hugging Face Job ${job.id}`}
              className="cron-info-text"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
          )}
        </div>
      </div>

      {progress ? (
        <>
          <div>
            <div className="flex justify-between gap-3 text-xs cron-muted mb-1">
              <span>{progress.processed_papers.toLocaleString()} / {progress.total_papers.toLocaleString()} papers</span>
              <span>{percentage.toFixed(0)}%</span>
            </div>
            <div className="cron-progress-track">
              <div className="cron-progress-value" style={{ width: `${percentage}%` }} />
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
            <span><strong>{progress.succeeded_papers.toLocaleString()}</strong> succeeded</span>
            <span><strong>{progress.failed_papers.toLocaleString()}</strong> failed</span>
            <span><strong>{progress.already_existed_papers.toLocaleString()}</strong> skipped</span>
            <span><strong>{progress.extracted_images.toLocaleString()}</strong> images</span>
          </div>
          {omittedImages > 0 && (
            <div className="text-xs cron-muted">
              <strong>{omittedImages.toLocaleString()}</strong> unresolved image references omitted after final retry
            </div>
          )}
          {progress.updated_at && (
            <div className="text-xs cron-muted">Progress updated {formatCronDate(progress.updated_at)}</div>
          )}
          {(progress.fatal_error || progress.error_samples.length > 0) && (
            <div className="cron-message cron-message--error space-y-1">
              {progress.fatal_error && <div>{progress.fatal_error}</div>}
              {progress.error_samples.map((item) => (
                <div key={`${item.arxiv_id}:${item.error}`}>
                  <span className="font-mono">{item.arxiv_id}</span>: {item.error}
                </div>
              ))}
            </div>
          )}
        </>
      ) : (
        <div className="text-sm cron-muted">
          Waiting for the shard progress checkpoint.
        </div>
      )}

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs cron-muted">
        {job.hardware && <span>{job.hardware}</span>}
        {job.created_at && <span>Created {formatCronDate(job.created_at)}</span>}
        {job.duration_seconds != null && <span>Duration {formatDuration(job.duration_seconds)}</span>}
      </div>
      {job.stage_message && <div className="cron-message cron-message--warning">{job.stage_message}</div>}
    </div>
  );
}

function PaperMarkdownJobs({
  monitor,
  loading,
  error,
}: {
  monitor?: PaperMarkdownJobsResponse;
  loading: boolean;
  error: unknown;
}) {
  return (
    <div className="md:col-span-2">
      <div className="cron-section-heading">
        <Images className="h-4 w-4" />
        <h4>Hugging Face OCR shards</h4>
      </div>
      {loading && (
        <div className="cron-metric-card flex items-center gap-2 text-sm cron-muted">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading remote Jobs…
        </div>
      )}
      {Boolean(error) && (
        <div className="cron-message cron-message--error">
          Could not load Hugging Face Jobs.
        </div>
      )}
      {monitor && !monitor.available && (
        <div className="cron-message cron-message--warning">
          {monitor.error ?? "Hugging Face monitoring is unavailable."}
        </div>
      )}
      {monitor?.available && (
        <>
          {monitor.budgets.live && monitor.budgets.backfill && (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 mb-3">
              <PaperMarkdownBudgetCard title="Live paper Markdown GPU policy" budget={monitor.budgets.live} profile={monitor.selected_profiles?.live} />
              <PaperMarkdownBudgetCard title="Full backfill GPU policy" budget={monitor.budgets.backfill} profile={monitor.selected_profiles?.backfill} />
            </div>
          )}
          <div className={`cron-message mb-3 ${(monitor.summary.unresolved_mount_failures ?? 0) > 0 ? "cron-message--error" : ""}`}>
            <strong>Logical shard health:</strong> {(monitor.summary.logical_shards ?? 0).toLocaleString()} logical shards / {(monitor.summary.provider_attempts ?? 0).toLocaleString()} provider attempts · {(monitor.summary.recovered_mount_failures ?? 0).toLocaleString()} recovered mount failures · {(monitor.summary.unresolved_mount_failures ?? 0).toLocaleString()} unresolved
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
            {Object.entries(monitor.summary).map(([key, value]) => (
              <div key={key} className="cron-metric-card">
                <div className="cron-label">{metricLabel(key)}</div>
                <div className="text-lg font-semibold">{value.toLocaleString()}</div>
              </div>
            ))}
          </div>
          <p className="text-xs cron-muted mb-3">
            Efficiency and backlog-clearance costs are admission-control estimates, not provider invoices.
          </p>
          {monitor.coverage && Object.keys(monitor.coverage).length > 0 && (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 mb-3">
              {Object.values(monitor.coverage).map((coverage) => (
                <div key={coverage.scope} className="cron-metric-card space-y-2 text-sm">
                  <div className="font-semibold">
                    {coverage.scope === "full" ? "Full catalog coverage" : "Recent 14-day coverage"}
                  </div>
                  <div className="text-lg font-semibold">{coverage.coverage_percentage.toFixed(2)}%</div>
                  <div>{coverage.canonical_markdown_count.toLocaleString()} canonical / {coverage.eligible_papers.toLocaleString()} eligible · {coverage.missing_count.toLocaleString()} missing</div>
                  <div className="cron-muted">Copied from upstream this reconciliation: {coverage.copied_from_upstream_count.toLocaleString()}</div>
                  <div className="cron-muted">
                    7-day Δ eligible {coverage.eligible_delta_7d ?? "collecting"} · canonical {coverage.canonical_delta_7d ?? "collecting"} · missing {coverage.missing_delta_7d ?? "collecting"}
                  </div>
                </div>
              ))}
            </div>
          )}
          {monitor.jobs.length === 0 ? (
            <div className="cron-metric-card text-sm cron-muted">
              No OCR shards have been launched yet.
            </div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
              {monitor.jobs.map((job) => <PaperMarkdownShard key={job.id} job={job} />)}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function CronJobCard({
  job,
  expanded,
  onToggle,
  autoRefresh = false,
}: {
  job: CronJobStatus;
  expanded: boolean;
  onToggle: () => void;
  autoRefresh?: boolean;
}) {
  const hasWorkMetrics = Boolean(job.work_metrics && Object.keys(job.work_metrics).length);
  const hasDbMetrics = Boolean(job.db_metrics && Object.keys(job.db_metrics).length);
  const hasRemoteJobs = job.job_name === "paper_markdown_backfill";
  const paperMarkdownJobs = useQuery({
    queryKey: adminQueryKeys.paperMarkdownJobs,
    queryFn: () => operationsApi.getPaperMarkdownJobs(),
    enabled: hasRemoteJobs,
    refetchInterval: autoRefresh ? 30000 : false,
    retry: false,
  });
  const livePaperMarkdownBudget = hasRemoteJobs ? paperMarkdownJobs.data?.budgets.live : undefined;
  const livePaperMarkdownUnmetered = livePaperMarkdownBudget?.cost_policy === "unmetered_hf" || livePaperMarkdownBudget?.budget_enforced === false;
  return (
    <div className="cron-job-card">
      <button type="button" className="cron-job-summary" onClick={onToggle} aria-expanded={expanded}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 flex-1 min-w-0">
            <Status status={job.status} isRunning={job.is_running} />
            <div className="flex-1 min-w-0 text-left">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <h3 className="font-semibold">{job.display_name}</h3>
                {job.critical && <Badge variant="outline" className="text-[10px] uppercase tracking-wide">Critical</Badge>}
                {job.lock_stale && <StatusBadge tone="broken">Held lock</StatusBadge>}
                <AxisBadge label="Execution" axis={job.execution_health} />
                <AxisBadge label="Output" axis={job.output_health} />
                {expanded ? <ChevronUp className="h-4 w-4 cron-muted" /> : <ChevronDown className="h-4 w-4 cron-muted" />}
              </div>
              <p className="text-sm cron-muted mb-2">{job.status_reason}</p>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-2 text-sm cron-muted">
                <span className="cron-fact"><Clock />Log: {formatCronDate(job.last_run)}</span>
                <span className="cron-fact"><Database />DB: {formatCronDate(job.last_db_write)}</span>
                {job.recent_write_count != null && <span className="cron-fact"><TrendingUp />Recent writes: {job.recent_write_count.toLocaleString()}</span>}
                {job.duration != null && <span className="cron-fact"><Activity />Duration: {formatDuration(job.duration)}</span>}
                {job.schedule && <span className="cron-fact md:col-span-2"><Calendar /><span className="font-mono text-xs">{job.schedule}</span></span>}
                {job.log_status && <span className="cron-fact"><FileText />Log status: {job.log_status}</span>}
                {job.workflow_status && <span className="cron-fact"><Activity />Actions: {formatWorkflowStatus(job.workflow_status)}</span>}
              </div>
              {job.work_summary && <div className="cron-message">{job.work_summary}</div>}
              {job.error && <div className="cron-message cron-message--error"><strong>Error: </strong>{job.error}</div>}
              {job.diagnostics && <div className="cron-message cron-message--warning">{job.diagnostics}</div>}
              {livePaperMarkdownBudget && (
                <div className={`cron-message ${livePaperMarkdownBudget.can_launch_planned ? "" : "cron-message--error"}`}>
                  <strong>Live GPU policy:</strong> {livePaperMarkdownUnmetered ? "unmetered on HF" : `${formatUsd(livePaperMarkdownBudget.current_exposure_usd)} current / ${formatUsd(livePaperMarkdownBudget.ceiling_usd)} cap`} · {livePaperMarkdownBudget.affordable_jobs} of {livePaperMarkdownBudget.desired_jobs} planned{livePaperMarkdownUnmetered ? "" : ` · projects ${formatUsd(livePaperMarkdownBudget.projected_usd)} · rolling 30 days`}
                </div>
              )}
            </div>
          </div>
          <StatusBadge tone={job.status}>{job.status}</StatusBadge>
        </div>
      </button>

      {expanded && (
        <div className="cron-job-details">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="cron-section-heading">
                <Calendar className="h-4 w-4" />
                <h4>Scheduler evidence</h4>
              </div>
              <div className="cron-metric-card space-y-2 text-sm">
                {[
                  ["Scheduler", job.execution_health.scheduler ?? "unknown"],
                  ["Last expected", formatCronDate(job.execution_health.last_expected_at ?? null)],
                  ["Last started", formatCronDate(job.execution_health.last_started_at ?? null)],
                  ["Last completed", formatCronDate(job.execution_health.last_completed_at ?? null)],
                  ["Next expected", formatCronDate(job.execution_health.next_expected_at ?? null)],
                ].map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between gap-3">
                    <span className="cron-label">{label}</span>
                    <span>{value}</span>
                  </div>
                ))}
              </div>
            </div>
            {job.work_metrics && hasWorkMetrics && <MetricGroup icon={FileText} title="Log Metrics" metrics={job.work_metrics} />}
            {job.db_metrics && hasDbMetrics && <MetricGroup icon={Database} title="Database Metrics" metrics={job.db_metrics} />}
            {job.workflow_status && <WorkflowDetails workflow={job.workflow_status} />}
            {hasRemoteJobs && (
              <PaperMarkdownJobs
                monitor={paperMarkdownJobs.data}
                loading={paperMarkdownJobs.isLoading}
                error={paperMarkdownJobs.error}
              />
            )}
            {job.diagnostic_groups && Object.values(job.diagnostic_groups).some((items) => items.length > 0) && (
              <div className="md:col-span-2">
                <div className="cron-section-heading">
                  <AlertTriangle className="h-4 w-4" />
                  <h4>Diagnostics by cause</h4>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {Object.entries(job.diagnostic_groups).filter(([, items]) => items.length > 0).map(([cause, items]) => (
                    <div key={cause} className="cron-metric-card">
                      <div className="cron-label mb-1">{metricLabel(cause)}</div>
                      <ul className="list-disc pl-4 text-sm space-y-1">
                        {items.map((item) => <li key={item}>{item}</li>)}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {job.health_findings && job.health_findings.some((finding) => finding.state !== "healthy") && (
              <div className="md:col-span-2">
                <div className="cron-section-heading">
                  <ShieldAlert className="h-4 w-4" />
                  <h4>Deterministic contract findings</h4>
                </div>
                <div className="cron-metric-card space-y-3 text-sm">
                  {job.health_findings.filter((finding) => finding.state !== "healthy").map((finding) => (
                    <div key={`${finding.plane}-${finding.contract}`}>
                      <StatusBadge tone={finding.state}>{finding.state}</StatusBadge>{" "}
                      <strong>{metricLabel(finding.contract)}</strong>: {finding.summary}
                      {Object.entries(finding.evidence).length > 0 && (
                        <div className="mt-1 text-xs cron-muted">
                          {Object.entries(finding.evidence).map(([key, value]) => (
                            <span className="mr-3" key={key}>{metricLabel(key)}: {String(value)}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                  <div className="flex gap-4">
                    {job.operator_url && <a className="cron-info-text inline-flex items-center gap-1" href={job.operator_url}>Open operator <ExternalLink className="h-3.5 w-3.5" /></a>}
                    {job.run_url && <a className="cron-info-text inline-flex items-center gap-1" href={job.run_url} target="_blank" rel="noreferrer">Open run <ExternalLink className="h-3.5 w-3.5" /></a>}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

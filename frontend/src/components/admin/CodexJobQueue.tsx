import { Link } from "react-router-dom";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  CircleSlash2,
  Clock3,
  ExternalLink,
  FileClock,
  Loader2,
  PlayCircle,
  XCircle,
} from "lucide-react";

import { StatusBadge } from "@/components/cron/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  AWAITING_MARKDOWN_MESSAGE,
  codexApi,
  type CodexPaperJob,
  type CodexPaperJobStatus,
} from "@/lib/api/codex";
import { ApiError } from "@/lib/apiTransport";
import { formatCronDate, type Tone } from "@/lib/cronStatus";
import { adminQueryKeys } from "@/lib/api/queryKeys";

const statusTones: Record<CodexPaperJobStatus, Tone> = {
  queued: "unknown",
  dispatching: "running",
  running: "running",
  completed: "healthy",
  failed: "broken",
  canceled: "unknown",
  awaiting_markdown: "unknown",
};

const statusLabels: Record<CodexPaperJobStatus, string> = {
  queued: "queued",
  dispatching: "dispatching",
  running: "running",
  completed: "completed",
  failed: "failed",
  canceled: "canceled",
  awaiting_markdown: "waiting for Markdown",
};

const kindLabels: Record<CodexPaperJob["kind"], string> = {
  "add-evals": "Add evals",
  "enrich-paper": "Enrich paper",
  "resolve-model-paper": "Resolve model release",
  "review-benchmark-gaps": "Review benchmark gaps",
  "add-benchmark": "Add benchmark",
};

const statusIcons: Record<CodexPaperJobStatus, typeof Clock3> = {
  queued: Clock3,
  dispatching: Loader2,
  running: PlayCircle,
  completed: CheckCircle2,
  failed: XCircle,
  canceled: CircleSlash2,
  awaiting_markdown: FileClock,
};

function JobStatus({ status }: { status: CodexPaperJobStatus }) {
  const Icon = statusIcons[status];
  return (
    <StatusBadge tone={statusTones[status]}>
      <Icon className={`mr-1 h-3.5 w-3.5 ${status === "dispatching" ? "animate-spin" : ""}`} />
      {statusLabels[status]}
    </StatusBadge>
  );
}

function resultText(job: CodexPaperJob) {
  if (job.status === "awaiting_markdown") return AWAITING_MARKDOWN_MESSAGE;
  if (job.error) return job.error;
  if (job.report) return job.report;
  if (job.status === "completed" && job.applied_at) return "Changes applied to the paper.";
  if (job.status === "completed") return "Completed without a recorded mutation.";
  return null;
}

type SkippedLeaderboard = {
  benchmark?: string;
  disposition?: string;
  task_id?: number;
  dataset_id?: number;
  metric?: string | null;
  value?: number | null;
  detail?: string;
};

function SkippedLeaderboards({ mutationResult }: { mutationResult: Record<string, unknown> | null }) {
  const skipped = mutationResult?.skipped_configured_leaderboards;
  if (!Array.isArray(skipped) || skipped.length === 0) return null;
  return (
    <div className="mt-2 rounded border border-amber-500 bg-amber-50 p-2 text-xs text-amber-900">
      <div className="font-medium">Skipped configured leaderboards ({skipped.length})</div>
      <ul className="mt-1 list-disc space-y-1 pl-4">
        {(skipped as SkippedLeaderboard[]).map((item, index) => (
          <li key={index}>
            {item.benchmark} · {item.disposition} · task {item.task_id} / dataset {item.dataset_id}
            {item.metric ? ` / ${item.metric}` : ""}
            {item.value != null ? ` = ${item.value}` : ""}
            {item.detail ? ` — ${item.detail}` : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CodexJobQueue({ autoRefresh }: { autoRefresh: boolean }) {
  const queryClient = useQueryClient();
  const [trigger, setTrigger] = useState("");
  const [status, setStatus] = useState("");
  const [policyVersion, setPolicyVersion] = useState("");
  const [cohortDate, setCohortDate] = useState("");
  const [reviewStatus, setReviewStatus] = useState("");
  const [promotionInputs, setPromotionInputs] = useState<Record<string, { dataset: string; task: string; metric: string }>>({});
  const filters = { trigger, status, policy_version: policyVersion, cohort_date: cohortDate, review_status: reviewStatus };
  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: [...adminQueryKeys.codexPaperJobs, filters],
    queryFn: () => codexApi.listJobs(100, filters),
    refetchInterval: autoRefresh ? 10_000 : false,
    retry: false,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: adminQueryKeys.codexPaperJobs });
  const retryJob = useMutation({ mutationFn: (id: string) => codexApi.retryJob(id), onSuccess: refresh });
  const cancelJob = useMutation({ mutationFn: (id: string) => codexApi.cancelJob(id), onSuccess: refresh });
  const retryTrace = useMutation({ mutationFn: (id: string) => codexApi.retryTrace(id), onSuccess: refresh });
  const scheduler = useMutation({
    mutationFn: (action: "pause" | "resume") => codexApi.setScheduler(action),
    onSuccess: refresh,
  });
  const promoteCandidate = useMutation({
    mutationFn: ({ id, dataset, task, metric }: { id: string; dataset: string; task: string; metric: string }) =>
      codexApi.promoteBenchmarkCandidate(id, { dataset_id: Number(dataset), task_id: Number(task), best_metric: metric.trim() }),
    onSuccess: refresh,
  });
  const rollbackCandidate = useMutation({
    mutationFn: (id: string) => codexApi.rollbackBenchmarkCandidate(id),
    onSuccess: refresh,
  });

  const notEnabled = error instanceof ApiError && error.status === 404;

  return (
    <Card className="mb-8">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-xl">Codex paper jobs</CardTitle>
            <CardDescription>
              Durable queue, two-stage daily workflows, traces, and benchmark-gap follow-up
            </CardDescription>
          </div>
          {isFetching && !isLoading && (
            <span className="flex items-center gap-2 text-xs cron-muted">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Syncing with Hugging Face
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="flex items-center justify-center py-10 cron-muted">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading paper jobs…
          </div>
        )}

        {error && !notEnabled && (
          <div className="cron-message cron-message--error mb-4">
            {error.message}
          </div>
        )}

        {notEnabled && (
          <p className="py-4 text-sm cron-muted">Codex paper jobs are not enabled in this environment.</p>
        )}

        {data && (
          <>
            <div className={`cron-message mb-5 ${data.scheduler.paused_at ? "cron-message--error" : ""}`}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <strong>Scheduled dispatch: {data.scheduler.paused_at ? "paused" : data.scheduler.dispatch_enabled ? "enabled" : "disabled"}</strong>
                  {data.scheduler.pause_reason && <div className="mt-1 text-xs">{data.scheduler.pause_reason}</div>}
                  <div className="mt-1 text-xs cron-muted">
                    Canary {data.scheduler.canary_released ? "released" : "active"} · Queue age {data.scheduler.queue_age_level}
                  </div>
                  <div className="mt-1 text-xs cron-muted">
                    Scheduled usage today {data.scheduler.usage.current_day_tokens.toLocaleString()} tokens · {data.scheduler.usage.mode === "enforced"
                      ? `pause threshold ${data.scheduler.usage.pause_threshold_tokens?.toLocaleString() ?? "not established"}`
                      : "first-week alert-only baseline"} · trailing median {data.scheduler.usage.trailing_seven_day_median_tokens.toLocaleString()}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant={data.scheduler.paused_at || !data.scheduler.dispatch_enabled ? "default" : "outline"}
                  disabled={scheduler.isPending}
                  onClick={() => scheduler.mutate(data.scheduler.paused_at || !data.scheduler.dispatch_enabled ? "resume" : "pause")}
                >
                  {data.scheduler.paused_at ? "Acknowledge & resume" : !data.scheduler.dispatch_enabled ? "Enable scheduled dispatch" : "Pause scheduled dispatch"}
                </Button>
              </div>
            </div>
            <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
              {(["queued", "awaiting_markdown", "dispatching", "running", "completed", "failed", "canceled"] as const).map(
                (status) => (
                  <div className="cron-metric-card" key={status}>
                    <div className="cron-label capitalize">{statusLabels[status]}</div>
                    <div className="mt-1 text-xl font-semibold">{data.summary[status]}</div>
                  </div>
                ),
              )}
              <div className="cron-metric-card">
                <div className="cron-label">Total</div>
                <div className="mt-1 text-xl font-semibold">{data.summary.total}</div>
              </div>
            </div>
            <div className="mb-5 grid gap-3 sm:grid-cols-5">
              <select aria-label="Trigger" className="rounded border px-2 py-1 text-sm" value={trigger} onChange={(event) => setTrigger(event.target.value)}>
                <option value="">All triggers</option><option value="admin">Admin</option><option value="hf-daily-cron">HF daily cron</option><option value="hf-trending-cron">HF trending cron</option><option value="benchmark-gap-cron">Benchmark gap cron</option><option value="model-release-radar">Release radar</option>
              </select>
              <select aria-label="Status" className="rounded border px-2 py-1 text-sm" value={status} onChange={(event) => setStatus(event.target.value)}>
                <option value="">All statuses</option>{Object.keys(statusTones).map((value) => <option key={value}>{value}</option>)}
              </select>
              <input aria-label="Policy version" className="rounded border px-2 py-1 text-sm" placeholder="Policy version" value={policyVersion} onChange={(event) => setPolicyVersion(event.target.value)} />
              <input aria-label="Cohort date" type="date" className="rounded border px-2 py-1 text-sm" value={cohortDate} onChange={(event) => setCohortDate(event.target.value)} />
              <select aria-label="Review status" className="rounded border px-2 py-1 text-sm" value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value)}>
                <option value="">All review states</option><option value="unreviewed">Unreviewed</option><option value="approved">Approved</option><option value="corrected">Corrected</option>
              </select>
            </div>

            {data.jobs.length === 0 ? (
              <p className="py-8 text-center text-sm cron-muted">No paper curation jobs have been submitted yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Status</TableHead>
                    <TableHead>Paper</TableHead>
                    <TableHead>Action</TableHead>
                    <TableHead>Requested</TableHead>
                    <TableHead>Execution</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.jobs.map((job) => {
                    const detail = resultText(job);
                    return (
                      <TableRow key={job.id}>
                        <TableCell className="align-top"><JobStatus status={job.status} /></TableCell>
                        <TableCell className="min-w-[260px] align-top">
                          {job.paper_route ? (
                            <>
                              <Link
                                to={`/paper/${encodeURIComponent(job.paper_route)}`}
                                className="font-medium hover:underline"
                              >
                                {job.paper_title}
                              </Link>
                              <div className="mt-1 text-xs cron-muted">Paper #{job.paper_id}</div>
                            </>
                          ) : job.kind === "review-benchmark-gaps" ? (
                            <span className="font-medium">Benchmark-gap backlog</span>
                          ) : job.kind === "add-benchmark" ? (
                            <>
                              <span className="font-medium">Benchmark candidate</span>
                              <div className="mt-1 text-xs cron-muted">{job.benchmark_candidate_id}</div>
                            </>
                          ) : job.release_signal_id ? (
                            <>
                              <span className="font-medium">Release radar signal</span>
                              <div className="mt-1 text-xs cron-muted">Signal {job.release_signal_id}</div>
                            </>
                          ) : (
                            <>
                              <span className="font-medium">Trending model discovery</span>
                              <div className="mt-1 text-xs cron-muted">Candidate {job.candidate_id}</div>
                            </>
                          )}
                        </TableCell>
                        <TableCell className="whitespace-nowrap align-top">
                          {kindLabels[job.kind]}
                          {job.applied_at && (
                            <div className="mt-1 flex items-center gap-1 text-xs cron-status--healthy">
                              <CheckCircle2 className="h-3.5 w-3.5" /> Applied
                            </div>
                          )}
                        </TableCell>
                        <TableCell className="whitespace-nowrap align-top">
                          <div>{formatCronDate(job.created_at)}</div>
                          <div className="mt-1 text-xs cron-muted">@{job.requested_by}</div>
                        </TableCell>
                        <TableCell className="max-w-[360px] align-top">
                          {job.hf_job_url ? (
                            <a
                              href={job.hf_job_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 hover:underline"
                            >
                              Hugging Face Job <ExternalLink className="h-3.5 w-3.5" />
                            </a>
                          ) : (
                            <span className="cron-muted">Waiting to dispatch</span>
                          )}
                          {detail && (
                            <p
                              className={`mt-2 line-clamp-3 text-xs ${job.error && job.status !== "awaiting_markdown" ? "text-red-700" : "cron-muted"}`}
                              title={detail}
                            >
                              {detail}
                            </p>
                          )}
                          <SkippedLeaderboards mutationResult={job.mutation_result} />
                          <div className="mt-2 flex gap-2">
                            {(["failed", "canceled"] as string[]).includes(job.status) && (
                              <Button size="sm" variant="outline" onClick={() => retryJob.mutate(job.id)}>Retry</Button>
                            )}
                            {(["queued", "awaiting_markdown", "dispatching", "running"] as string[]).includes(job.status) && (
                              <Button size="sm" variant="outline" onClick={() => cancelJob.mutate(job.id)}>Cancel</Button>
                            )}
                            {job.trace_status === "finalize_failed" && (
                              <Button size="sm" variant="outline" onClick={() => retryTrace.mutate(job.id)}>Retry trace</Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
            {data.workflows.length > 0 && (
              <div className="mt-8 space-y-3">
                <h3 className="text-base font-semibold">Scheduled paper workflows</h3>
                {data.workflows.map((workflow) => (
                  <details key={workflow.id} className="rounded-md border p-3">
                    <summary className="cursor-pointer text-sm font-medium">
                      Paper #{workflow.paper_id} · {workflow.cohort_date} · {workflow.status} · {workflow.policy_version}
                    </summary>
                    <div className="mt-3 space-y-3 text-xs">
                      {workflow.error && <div className="text-red-700">{workflow.error}</div>}
                      {workflow.stages.map((stage) => (
                        <div key={stage.id} className="rounded border p-3">
                          <div className="font-medium">{kindLabels[stage.kind]} · {stage.status} · trace {stage.trace_status} · review {stage.audit_status}</div>
                          <div className="mt-1 cron-muted">
                            model {stage.model ?? "—"} · reasoning {stage.reasoning_effort ?? "—"} · tokens {(stage.input_tokens ?? 0) + (stage.output_tokens ?? 0)} · duration {stage.duration_ms ?? 0} ms · attempts {stage.attempt_count}
                          </div>
                          {stage.error && <div className="mt-2 text-red-700">{stage.error}</div>}
                          {stage.report && <div className="mt-2 whitespace-pre-wrap rounded border p-2">{stage.report}</div>}
                          {stage.url_candidates && <details className="mt-2"><summary>URL candidates and provenance</summary><pre className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap">{JSON.stringify(stage.url_candidates, null, 2)}</pre></details>}
                          {stage.validation_summary && <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap">{JSON.stringify(stage.validation_summary, null, 2)}</pre>}
                          {Array.isArray(stage.validation_summary?.manual_or_legacy_evaluation_rows_affected) && stage.validation_summary.manual_or_legacy_evaluation_rows_affected.length > 0 && (
                            <div className="mt-2 rounded border border-amber-500 bg-amber-50 p-2 font-medium text-amber-900">
                              Manual or legacy evaluation rows changed: {stage.validation_summary.manual_or_legacy_evaluation_rows_affected.join(", ")}. Review the evidence and before/after diff.
                            </div>
                          )}
                          {stage.proposal && <pre className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap">{JSON.stringify(stage.proposal, null, 2)}</pre>}
                          <SkippedLeaderboards mutationResult={stage.mutation_result} />
                          {stage.mutation_result && <details className="mt-2"><summary>Accepted callback result and before/after state</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap">{JSON.stringify(stage.mutation_result, null, 2)}</pre></details>}
                          {stage.trace_status === "complete" && (
                            <a className="mt-2 inline-flex items-center gap-1 hover:underline" href={codexApi.traceUrl(stage.id)} target="_blank" rel="noreferrer">
                              Authenticated trace manifest <ExternalLink className="h-3.5 w-3.5" />
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            )}
            {data.benchmark_candidates.length > 0 && (
              <div className="mt-8 space-y-3">
                <h3 className="text-base font-semibold">Benchmark-gap backlog</h3>
                {data.benchmark_candidates.map((candidate) => {
                  const inputs = promotionInputs[candidate.id] ?? { dataset: "", task: candidate.task_ids[0]?.toString() ?? "", metric: "" };
                  const valid = Number(inputs.dataset) > 0 && Number(inputs.task) > 0 && inputs.metric.trim().length > 0;
                  return (
                    <div key={candidate.id} className="rounded-md border p-3 text-xs">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="font-medium">{candidate.canonical_name} · {candidate.gap_type} · {candidate.status}</div>
                        <div className="cron-muted">{candidate.distinct_paper_count} paper{candidate.distinct_paper_count === 1 ? "" : "s"} · {candidate.confidence ?? "unknown"} confidence</div>
                      </div>
                      {candidate.canonical_url && <a className="mt-1 block hover:underline" href={candidate.canonical_url} target="_blank" rel="noreferrer">{candidate.canonical_url}</a>}
                      <div className="mt-1 cron-muted">Task evidence: {candidate.task_ids.join(", ") || "none"} · Papers: {candidate.evidence_paper_ids.join(", ")}</div>
                      {candidate.review_reason && (
                        <div className="mt-1">
                          Review{candidate.reviewed_at ? ` ${formatCronDate(candidate.reviewed_at)}` : ""}: {candidate.review_reason}
                          {candidate.deferred_until && ` · deferred until ${formatCronDate(candidate.deferred_until)}`}
                        </div>
                      )}
                      {candidate.resolution && (
                        <div className="mt-1 cron-muted">
                          Dataset #{candidate.resolution.dataset_id} · task #{candidate.resolution.task_id} · {candidate.resolution.primary_metric}
                          {candidate.resolution.rolled_back_at && ` · rolled back ${formatCronDate(candidate.resolution.rolled_back_at)}`}
                        </div>
                      )}
                      {candidate.status === "promoted" && candidate.resolution?.created && !candidate.resolution.rolled_back_at && (
                        <Button className="mt-2" size="sm" variant="outline" disabled={rollbackCandidate.isPending} onClick={() => rollbackCandidate.mutate(candidate.id)}>
                          Roll back automatic benchmark
                        </Button>
                      )}
                      {!["promoted", "merged"].includes(candidate.status) && (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {(["dataset", "task", "metric"] as const).map((field) => (
                            <input
                              key={field}
                              aria-label={`${candidate.canonical_name} ${field}`}
                              className="w-36 rounded border px-2 py-1"
                              placeholder={field === "metric" ? "Exact metric" : `${field} ID`}
                              value={inputs[field]}
                              onChange={(event) => setPromotionInputs((current) => ({ ...current, [candidate.id]: { ...inputs, [field]: event.target.value } }))}
                            />
                          ))}
                          <Button size="sm" variant="outline" disabled={!valid || promoteCandidate.isPending} onClick={() => promoteCandidate.mutate({ id: candidate.id, ...inputs })}>Promote & requeue evidence papers</Button>
                        </div>
                      )}
                    </div>
                  );
                })}
                {promoteCandidate.error && <div className="cron-message cron-message--error">{promoteCandidate.error.message}</div>}
                {rollbackCandidate.error && <div className="cron-message cron-message--error">{rollbackCandidate.error.message}</div>}
              </div>
            )}
            <p className="mt-4 text-xs cron-muted">
              Showing the 100 most recent jobs · Queue totals include full history · Updated {formatCronDate(data.timestamp)}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

import { useQuery } from "@tanstack/react-query";

import { codexApi, type CodexPaperJob, type CodexSchedulerPause } from "@/lib/api/codex";
import { adminQueries } from "@/lib/api/queries";

import { CodexJobReport } from "./CodexPaperJobDialog";

function formatTime(value: string | null): string | null {
  return value ? new Date(value).toLocaleString() : null;
}

function JobTimeline({ job }: { job: CodexPaperJob }) {
  const steps = [
    ["created", job.created_at],
    ["started", job.started_at],
    ["submitted", job.submitted_at],
    ["applied", job.applied_at],
    ["finished", job.finished_at],
  ] as const;
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {steps.map(([label, value]) => value && (
        <span key={label}>{label} {formatTime(value)}</span>
      ))}
    </div>
  );
}

function JsonDetails({ label, value }: { label: string; value: Record<string, unknown> | null }) {
  if (!value) return null;
  return (
    <details>
      <summary className="cursor-pointer text-xs">{label}</summary>
      <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-muted/40 p-2 font-mono text-xs">
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}

function pauseMessage(pause: CodexSchedulerPause): string {
  const since = pause.paused_at ? ` since ${formatTime(pause.paused_at)}` : "";
  const reason = pause.pause_reason ?? pause.pause_condition ?? "dispatch disabled";
  return `Queued — scheduler dispatch paused${since}: ${reason}`;
}

function CurationJob({ job, pause }: { job: CodexPaperJob; pause: CodexSchedulerPause | null }) {
  return (
    <details className="rounded-md border p-3">
      <summary className="cursor-pointer text-sm">
        <span className="font-medium">{job.kind}</span>
        {" · "}
        <span className="font-mono text-xs uppercase">{job.status.replace("_", " ")}</span>
        {" · "}
        {job.trigger}
        {job.runner && job.runner !== "codex" ? ` · ${job.runner}` : ""}
        {" · "}
        <span className="text-muted-foreground">{formatTime(job.created_at)}</span>
      </summary>
      <div className="mt-3 min-w-0 space-y-3">
        {pause?.job_ids.includes(job.id) && (
          <div className="rounded-md border border-amber-500/50 bg-amber-500/10 p-2 text-sm">
            {pauseMessage(pause)}
          </div>
        )}
        <JobTimeline job={job} />
        <div className="flex flex-wrap gap-3 text-xs">
          <span>attempts {job.attempt_count}</span>
          <span>trace {job.trace_status}</span>
          {job.trace_status === "complete" && (
            <a className="underline" href={codexApi.traceUrl(job.id)} target="_blank" rel="noreferrer">
              trace manifest
            </a>
          )}
          {job.hf_job_url && (
            <a className="underline" href={job.hf_job_url} target="_blank" rel="noreferrer">
              Hugging Face Job
            </a>
          )}
        </div>
        {job.error && (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-sm text-destructive">
            {job.error}
          </div>
        )}
        {job.report && <CodexJobReport report={job.report} />}
        <JsonDetails label="Validation summary" value={job.validation_summary} />
        <JsonDetails label="Mutation result" value={job.mutation_result} />
      </div>
    </details>
  );
}

/** Admin-only list of the scheduled and manual curation jobs for one paper. */
export function PaperCurationHistory({ paperId }: { paperId: number }) {
  const history = useQuery({ ...adminQueries.paperCurationHistory(paperId), retry: false });
  const jobs = history.data?.jobs ?? [];
  const pause = history.data?.scheduler_pause ?? null;
  return (
    <details className="mt-8 rounded-md border p-4">
      <summary className="cursor-pointer text-sm font-medium">
        Curation history (admin)
        <span className="ml-2 font-normal text-muted-foreground">
          {history.isLoading ? "loading…" : `${jobs.length} job${jobs.length === 1 ? "" : "s"}`}
          {pause ? " · dispatch paused" : ""}
        </span>
      </summary>
      <div className="mt-3 space-y-2">
        {history.error && (
          <div className="text-sm text-destructive">{history.error.message}</div>
        )}
        {history.data && jobs.length === 0 && (
          <div className="text-sm text-muted-foreground">
            No enrich-paper or add-evals job has run for this paper.
          </div>
        )}
        {jobs.map((job) => <CurationJob key={job.id} job={job} pause={pause} />)}
      </div>
    </details>
  );
}

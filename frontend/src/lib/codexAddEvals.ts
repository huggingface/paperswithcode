import { apiUrl } from "@/lib/apiUrl";

export type CodexPaperJobStatus = "queued" | "dispatching" | "running" | "completed" | "failed" | "canceled";

interface CodexThumbnailResult {
  requested: boolean;
  status: "queued" | "processing" | "succeeded" | "failed";
  attempt_count: number;
  requested_at: string;
  claimed_at: string | null;
  finished_at: string | null;
  thumbnail_url: string | null;
  previous_dimensions: [number, number] | null;
  generated_dimensions: [number, number] | null;
  success: boolean | null;
  warnings: string[];
  error: string | null;
}

export interface CodexPaperJob {
  id: string;
  paper_id: number | null;
  candidate_id: string | null;
  benchmark_candidate_id: string | null;
  paper_route: string | null;
  paper_title: string | null;
  requested_by: string;
  kind: "add-evals" | "enrich-paper" | "resolve-model-paper" | "review-benchmark-gaps" | "add-benchmark";
  status: CodexPaperJobStatus;
  hf_job_id: string | null;
  hf_job_url: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  submitted_at: string | null;
  applied_at: string | null;
  report: string | null;
  error: string | null;
  attempt_count: number;
  thumbnail: CodexThumbnailResult | null;
  parent_workflow_id: string | null;
  trigger: "admin" | "hf-daily-cron" | "hf-trending-cron" | "benchmark-promotion" | "benchmark-gap-cron";
  cohort_date: string | null;
  policy_version: string;
  repository_sha: string | null;
  model: string | null;
  reasoning_effort: string | null;
  codex_cli_version: string | null;
  trace_status: string;
  trace_uri: string | null;
  proposal: Record<string, unknown> | null;
  validation_summary: Record<string, unknown> | null;
  mutation_result: Record<string, unknown> | null;
  url_candidates: {
    candidates?: Array<Record<string, unknown>>;
    sources?: Array<Record<string, unknown>>;
    errors?: Array<Record<string, unknown>>;
  } | null;
  input_tokens: number | null;
  output_tokens: number | null;
  duration_ms: number | null;
  audit_status: string;
}

interface CodexPaperWorkflow {
  id: string;
  paper_id: number;
  cohort_date: string;
  policy_version: string;
  status: string;
  review_status: string;
  dependency_override: boolean;
  deferred_reason: string | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  stages: CodexPaperJob[];
}

interface BenchmarkCurationCandidate {
  id: string;
  canonical_name: string;
  gap_type: string;
  canonical_url: string | null;
  task_ids: number[];
  aliases: string[];
  status: string;
  distinct_paper_count: number;
  confidence: string | null;
  first_seen_at: string;
  last_seen_at: string;
  promoted_at: string | null;
  review_reason: string | null;
  reviewed_at: string | null;
  deferred_until: string | null;
  merged_into_id: string | null;
  resolution: {
    dataset_id: number;
    task_id: number;
    primary_metric: string;
    created?: Record<string, unknown>;
    rolled_back_at?: string;
  } | null;
  evidence_paper_ids: number[];
}

export interface CodexPaperJobsResponse {
  timestamp: string;
  jobs: CodexPaperJob[];
  summary: Record<CodexPaperJobStatus, number> & { total: number };
  workflows: CodexPaperWorkflow[];
  benchmark_candidates: BenchmarkCurationCandidate[];
  scheduler: {
    dispatch_enabled: boolean;
    paused_at: string | null;
    pause_reason: string | null;
    pause_condition: string | null;
    canary_released: boolean;
    oldest_scheduled_queued_at: string | null;
    queue_age_level: "healthy" | "warning" | "critical";
    usage: {
      mode: "baseline_alert_only" | "enforced";
      current_day_tokens: number;
      trailing_seven_day_median_tokens: number;
      pause_threshold_tokens: number | null;
    };
  };
}

export async function promoteBenchmarkCandidate(
  candidateId: string,
  payload: { dataset_id: number; task_id: number; best_metric: string },
): Promise<void> {
  const response = await fetch(
    apiUrl(`/api/v1/admin/codex-curation/jobs/benchmark-candidates/${candidateId}/promote`),
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Could not promote benchmark candidate (${response.status}).`);
  }
}

export async function rollbackBenchmarkCandidate(candidateId: string): Promise<void> {
  const response = await fetch(
    apiUrl(`/api/v1/admin/codex-curation/jobs/benchmark-candidates/${candidateId}/rollback`),
    { method: "POST", credentials: "include" },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Could not roll back benchmark candidate (${response.status}).`);
  }
}

export function isCodexAddEvalsEnabled(): boolean {
  const value = String(import.meta.env.VITE_CODEX_ADD_EVALS_ENABLED ?? "").toLowerCase();
  return value === "1" || value === "true" || value === "yes";
}

export function isCodexEnrichPaperEnabled(): boolean {
  const value = String(import.meta.env.VITE_CODEX_ENRICH_PAPER_ENABLED ?? "").toLowerCase();
  return value === "1" || value === "true" || value === "yes";
}

async function readJobResponse(response: Response): Promise<CodexPaperJob> {
  if (response.ok) return (await response.json()) as CodexPaperJob;
  const body = await response.json().catch(() => null);
  const detail = body?.detail?.message ?? body?.detail;
  throw new Error(typeof detail === "string" ? detail : "Could not run Codex.");
}

export async function startCodexAddEvals(paperId: number): Promise<CodexPaperJob> {
  const response = await fetch(apiUrl("/api/v1/admin/codex-add-evals/jobs"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paper_id: paperId }),
  });
  return readJobResponse(response);
}

export async function getCodexAddEvalsJob(jobId: string): Promise<CodexPaperJob> {
  const response = await fetch(apiUrl(`/api/v1/admin/codex-add-evals/jobs/${jobId}`), {
    credentials: "include",
  });
  return readJobResponse(response);
}

export async function cancelCodexAddEvalsJob(jobId: string): Promise<CodexPaperJob> {
  return readJobResponse(await fetch(apiUrl(`/api/v1/admin/codex-add-evals/jobs/${jobId}`), {
    method: "DELETE", credentials: "include",
  }));
}

export async function startCodexEnrichPaper(paperId: number): Promise<CodexPaperJob> {
  const response = await fetch(apiUrl("/api/v1/admin/codex-enrich-paper/jobs"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paper_id: paperId }),
  });
  return readJobResponse(response);
}

export async function getCodexEnrichPaperJob(jobId: string): Promise<CodexPaperJob> {
  const response = await fetch(apiUrl(`/api/v1/admin/codex-enrich-paper/jobs/${jobId}`), {
    credentials: "include",
  });
  return readJobResponse(response);
}

export async function cancelCodexEnrichPaperJob(jobId: string): Promise<CodexPaperJob> {
  return readJobResponse(await fetch(apiUrl(`/api/v1/admin/codex-enrich-paper/jobs/${jobId}`), {
    method: "DELETE", credentials: "include",
  }));
}

export interface CodexJobFilters {
  trigger?: string;
  status?: string;
  policy_version?: string;
  cohort_date?: string;
  review_status?: string;
}

export async function getCodexPaperJobs(limit = 100, filters: CodexJobFilters = {}): Promise<CodexPaperJobsResponse> {
  const query = new URLSearchParams({ limit: String(limit) });
  Object.entries(filters).forEach(([key, value]) => { if (value) query.set(key, value); });
  const response = await fetch(
    apiUrl(`/api/v1/admin/codex-curation/jobs?${query}`),
    { credentials: "include", cache: "no-store" },
  );
  if (response.ok) return (await response.json()) as CodexPaperJobsResponse;
  const error = new Error(`Could not load Codex jobs (${response.status}).`);
  Object.assign(error, { status: response.status });
  throw error;
}

export async function retryCodexPaperJob(jobId: string): Promise<CodexPaperJob> {
  return readJobResponse(await fetch(apiUrl(`/api/v1/admin/codex-curation/jobs/${jobId}/retry`), {
    method: "POST", credentials: "include",
  }));
}

export async function retryCodexTrace(jobId: string): Promise<void> {
  const response = await fetch(apiUrl(`/api/v1/admin/codex-curation/jobs/${jobId}/retry-trace`), {
    method: "POST", credentials: "include",
  });
  if (!response.ok) throw new Error(`Could not retry trace upload (${response.status}).`);
}

export async function cancelCodexPaperJob(jobId: string): Promise<CodexPaperJob> {
  return readJobResponse(await fetch(apiUrl(`/api/v1/admin/codex-curation/jobs/${jobId}`), {
    method: "DELETE", credentials: "include",
  }));
}

export async function setCodexScheduler(action: "pause" | "resume"): Promise<void> {
  const response = await fetch(apiUrl(`/api/v1/admin/codex-curation/jobs/scheduler/${action}`), {
    method: "POST", credentials: "include",
  });
  if (!response.ok) throw new Error(`Could not ${action} scheduled curation (${response.status}).`);
}

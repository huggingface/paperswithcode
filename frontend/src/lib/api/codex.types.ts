export type CodexPaperJobStatus =
  | "queued"
  | "dispatching"
  | "running"
  | "completed"
  | "failed"
  | "canceled"
  | "awaiting_markdown";

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
  release_signal_id?: string | null;
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
  trigger: "admin" | "hf-daily-cron" | "hf-trending-cron" | "benchmark-promotion" | "benchmark-gap-cron" | "model-release-radar";
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

export interface CodexPaperWorkflow {
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

export interface BenchmarkCurationCandidate {
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

export interface CodexJobFilters {
  trigger?: string;
  status?: string;
  policy_version?: string;
  cohort_date?: string;
  review_status?: string;
}

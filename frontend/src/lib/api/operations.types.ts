export type CronJobHealth = 'healthy' | 'degraded' | 'broken' | 'running' | 'stuck' | 'unknown';

export interface CronHealthAxis {
  status: CronJobHealth;
  reason: string;
  scheduler?: 'github_actions' | 'systemd' | 'manual';
  last_expected_at?: string | null;
  last_started_at?: string | null;
  last_completed_at?: string | null;
  next_expected_at?: string | null;
  last_verified_at?: string | null;
}

export interface CronWorkflowStatus {
  available: boolean;
  workflow_file: string;
  run_id?: number | null;
  status?: string | null;
  conclusion?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  event?: string | null;
  failed_jobs?: string[];
  running_jobs?: string[];
  job_conclusions?: Record<string, string | null>;
  error?: string | null;
  view_error?: string | null;
}

export interface CronJobStatus {
  job_name: string;
  display_name: string;
  category: string;
  dashboard_group: 'operations' | 'leaderboard_sync';
  status: CronJobHealth;
  log_status?: string | null;
  status_reason: string;
  last_run: string | null;
  last_db_write: string | null;
  recent_write_count: number | null;
  duration: number | null;
  is_running: boolean;
  error: string | null;
  schedule: string | null;
  critical: boolean;
  work_metrics?: Record<string, string | number>;
  work_summary?: string | null;
  db_metrics?: Record<string, string | number>;
  workflow_status?: CronWorkflowStatus | null;
  systemd_status?: Record<
    string,
    string | number | boolean | string[] | null
  > | null;
  execution_health: CronHealthAxis;
  output_health: CronHealthAxis;
  lock_state?: Record<string, string | number | boolean | null>;
  lock_stale?: boolean;
  diagnostics?: string | null;
  diagnostic_groups?: Record<string, string[]>;
  health_findings?: Array<{
    plane: 'scheduler' | 'process_logs' | 'durable_data' | 'semantic_outcome';
    contract: string;
    state: 'healthy' | 'degraded' | 'unknown';
    summary: string;
    evidence: Record<string, unknown>;
  }>;
  operator_url?: string | null;
  run_url?: string | null;
}

export interface CronJobsResponse {
  timestamp: string;
  jobs: CronJobStatus[];
  manual_operations: CronJobStatus[];
  snapshot_generated_at: string;
  snapshot_age_seconds: number;
  snapshot_stale: boolean;
  refreshing: boolean;
  summary: Record<CronJobHealth, number> & {
    total_jobs: number;
    scheduled_jobs: number;
    manual_jobs: number;
    health_score: number;
    critical_issues: string[];
    what_to_check_next: string;
    coverage: {
      registered_scheduled_duties: number;
      discovered_scheduled_duties: number;
      monitored_duties: number;
      coverage_gaps: number;
      gap_ids?: string[];
    };
  };
}


export interface PaperMarkdownJobProgress {
  status: string;
  total_papers: number;
  processed_papers: number;
  succeeded_papers: number;
  failed_papers: number;
  already_existed_papers: number;
  extracted_images: number;
  omitted_images?: number;
  updated_at?: string | null;
  started_at?: string | null;
  fatal_error?: string | null;
  error_samples: Array<{ arxiv_id: string; error: string }>;
}

export interface PaperMarkdownRemoteJob {
  id: string;
  url: string;
  stage: string;
  stage_message?: string | null;
  mode?: string | null;
  run_id?: string | null;
  shard_id?: string | null;
  provider_attempt?: number;
  profile_id?: string | null;
  hardware?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_seconds?: number | null;
  effective_outcome?: string;
  failure_cause?: string | null;
  progress?: PaperMarkdownJobProgress | null;
}

export interface PaperMarkdownLogicalShard {
  run_id: string;
  shard_id: string;
  mode?: string | null;
  profile_id?: string | null;
  provider_attempts: number;
  provider_job_ids: string[];
  latest_provider_job_id: string;
  effective_outcome: string;
  failure_cause?: string | null;
  recovered_mount_failure: boolean;
  unresolved_mount_failure: boolean;
  requires_operator_ack: boolean;
  created_at?: string | null;
}

export interface PaperMarkdownJobProfile {
  profile_id: string;
  mode: "live" | "backfill";
  max_papers: number;
  concurrency: number;
  hard_timeout_seconds: number;
  soft_deadline_seconds: number;
  reservation_hours: number;
  reservation_per_job_usd: number;
}

export interface PaperMarkdownJobsResponse {
  available: boolean;
  namespace: string;
  updated_at?: string | null;
  jobs: PaperMarkdownRemoteJob[];
  logical_shards?: PaperMarkdownLogicalShard[];
  summary: Record<string, number>;
  budgets: Record<string, PaperMarkdownBudget>;
  selected_profiles?: Record<string, PaperMarkdownJobProfile>;
  blockers?: Record<string, "none" | "budget" | "reliability" | "reliability_and_budget">;
  retry_dispositions?: Record<string, number>;
  coverage?: Record<string, PaperMarkdownCoverage>;
  error?: string | null;
}

export interface PaperMarkdownCoverage {
  observed_at: string;
  scope: string;
  eligible_papers: number;
  canonical_markdown_count: number;
  copied_from_upstream_count: number;
  missing_count: number;
  coverage_percentage: number;
  eligible_delta_7d?: number | null;
  canonical_delta_7d?: number | null;
  missing_delta_7d?: number | null;
}

export interface PaperMarkdownBudget {
  mode: "live" | "backfill";
  cost_policy?: "metered" | "unmetered_hf";
  budget_enforced?: boolean;
  window: "rolling_30_days" | "all_history";
  window_days: number | null;
  window_started_at: string | null;
  next_release_at: string | null;
  next_release_usd: number;
  next_admission_at?: string | null;
  spent_usd: number;
  active_reserved_usd: number;
  unknown_terminal_reservation_count?: number;
  unknown_terminal_reservation_usd?: number;
  desired_jobs: number;
  affordable_jobs: number;
  planned_jobs: number;
  planned_reserved_usd: number;
  current_exposure_usd: number;
  projected_usd: number;
  ceiling_usd: number;
  headroom_usd: number;
  can_launch_planned: boolean;
  hourly_rate_usd: number;
  reservation_hours_per_job: number;
  reservation_per_job_usd: number;
  profile?: PaperMarkdownJobProfile;
  relevant_jobs: number;
  reason?: string | null;
}

export type AutonomousDisplayState =
  | "healthy"
  | "degraded"
  | "repairing"
  | "rolled-back"
  | "manual";

export interface AutonomousOperationsResponse {
  revision: number;
  manual_mode: boolean;
  monitoring_active: boolean;
  display_state: AutonomousDisplayState;
  operators: Array<{
    operator: "submissions" | "curation" | "cron_health" | "chat_reliability";
    enabled: boolean;
    status: AutonomousDisplayState;
    monitoring_active: boolean;
    next_scheduled_run: string | null;
  }>;
  active_lease: {
    lease_id: string;
    owner_run_id: string;
    owner_operator: "cron_health" | "chat_reliability";
    expires_at: string;
  } | null;
  costs: { input_tokens: number; output_tokens: number; total_usd: string };
  baseline: {
    sha: string;
    revision: number;
    qualified_by: string;
    qualified_at: string;
  } | null;
  provider_states: Array<{
    environment: "staging" | "production";
    manifest_revision: string;
    state_revision: number;
    active_provider: string;
    reason_code: string;
    updated_at: string;
  }>;
  recent_runs: Array<{
    run_id: string;
    operator: "submissions" | "curation" | "cron_health" | "chat_reliability";
    dry_run: boolean;
    status: string;
    exit_classification: string;
    input_tokens: number;
    output_tokens: number;
    cost_usd: string;
    created_at: string;
  }>;
  recent_actions: Array<{
    action_id: string;
    run_id: string;
    operator: "submissions" | "curation" | "cron_health" | "chat_reliability";
    capability: string;
    reason_code: string;
    resource_kind: string;
    resource_identifier: string;
    created_at: string;
  }>;
  exclusions: string[];
}

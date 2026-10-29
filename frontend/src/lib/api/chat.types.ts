export interface OpenRouterUsageStatus {
  used_percent: number;
  remaining_percent: number;
  resets_at: string;
  available: boolean;
  unavailable_reason: "personal_allowance_exhausted" | "workspace_limit_exhausted" | "shared_credits_exhausted" | "provider_status_unavailable" | "staging_funding_disabled" | null;
  production_chat_url?: string;
  as_of: string;
}

export interface OpenAIUsageStatus {
  used_percent: number;
  remaining_percent: number;
  resets_at: string;
  available: boolean;
  as_of: string;
}

export interface OpenRouterCredentialStatus {
  connected: boolean;
  verified_at: string | null;
  fallback_enabled: boolean;
}


export interface ChatAvailability {
  status: 'available' | 'paused';
  reason: 'chat_temporarily_disabled' | null;
  expected_recovery_at: string | null;
  paper_mentions_enabled: boolean;
  web_search_available: boolean;
  native_pdf_reader_enabled?: boolean;
  paper_reader_chat_enabled?: boolean;
  paper_reader_selection_enabled?: boolean;
  paper_reader_citations_enabled?: boolean;
  paper_artifacts_enabled?: boolean;
}

export interface ChatAutocompleteVocabulary {
  names: string[];
}

export interface ChatSandboxSpendStatus {
  environment: string;
  provider_mode: 'starter_workspace' | 'team_environments';
  billing_cycle: string;
  cycle_end_at: string;
  circuit_state: 'armed' | 'warning' | 'tripped';
  trip_reason: string | null;
  tripped_at: string | null;
  estimated_microusd: number;
  provider_floor_microusd: number;
  effective_microusd: number;
  warning_microusd: number;
  application_cap_microusd: number;
  environment_cap_microusd: number | null;
  workspace_cap_microusd: number;
  remaining_microusd: number;
  reconciliation_state: 'fresh' | 'stale' | 'unavailable';
  last_metered_at: string | null;
  last_reconciled_at: string | null;
  last_reconciliation_attempt_at: string | null;
  next_reconciliation_at: string | null;
  live_count: number;
  termination_uncertain_count: number;
  live_states: Record<'starting' | 'blank' | 'busy' | 'idle' | 'draining' | 'termination_uncertain', number>;
  burn_rate_microusd_per_hour: number | null;
  projected_cap_hit_at: string | null;
  prior_cycle: {
    billing_cycle: string;
    estimated_microusd: number;
    provider_floor_microusd: number;
    effective_microusd: number;
  } | null;
  daily_spend: Array<{ date: string; blank_pool_microusd: number; assigned_microusd: number }>;
  events: Array<{ id: string; type: string; severity: string; reason: string | null; created_at: string; details: Record<string, unknown> }>;
}

export interface ChatWebSearchBudgetStatus {
  environment: string;
  billing_cycle: string;
  cycle_end_at: string;
  available: boolean;
  warning_calls: number;
  hard_limit_calls: number;
  call_count: number;
  remaining_calls: number;
  success_count: number;
  failure_count: number;
  provider_cost_microusd: number;
  last_latency_ms: number | null;
  last_result_count: number | null;
  circuit_state: 'armed' | 'warning' | 'cooldown' | 'tripped';
  trip_reason: string | null;
  cooldown_until: string | null;
  last_provider_error_class: string | null;
  events: Array<{
    id: string;
    type: string;
    error_class: string | null;
    created_at: string;
    details: Record<string, unknown>;
  }>;
}

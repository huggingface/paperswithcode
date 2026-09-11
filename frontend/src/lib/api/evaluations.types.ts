export interface Evaluation {
  id: string;
  paper_id: string;
  task_id: string;
  dataset_id: string;
  model_name?: string;
  /** Optional harness/runtime used to evaluate the model
   *  (e.g. "Claude Code", "Terminus"). Surfaced alongside the model on
   *  benchmark leaderboards for model+harness benchmarks like Terminal-Bench. */
  harness?: string;
  methodology?: string;
  metrics: Record<string, string | number>;
  uses_additional_data: boolean;
  /** Whether the evaluated model is open-source. True by default; false for
   *  closed-source models (proprietary APIs, unreleased flagship LLMs). */
  is_open: boolean;
  best_rank?: number;
  best_metric?: string;
  evaluated_on?: string;
  external_source_url?: string;
  source_url?: string;
  /** True when the score source is independent of the evaluated paper/model. */
  external?: boolean;
  /** Legacy alias for external. */
  is_external?: boolean;
  /** Raw number of model parameters (e.g. 7000000000 for a 7B model).
   *  Optional metadata used by future leaderboards to filter and visualize
   *  results by model size. */
  num_parameters?: number | null;
  /** Optional Hugging Face model page for the evaluated model
   *  (e.g. "https://huggingface.co/MiniMaxAI/MiniMax-M3"). When present, the
   *  model name is rendered as a link to this page. */
  hf_model_url?: string | null;
  created_at: string;
  updated_at: string;
  paper_title?: string;
  paper_arxiv_id?: string;
  paper_published_date?: string;
  code_url?: string;
  result_url?: string;
  task_name?: string;
  task_slug?: string;
  dataset_name?: string;
  dataset_slug?: string;
}

export interface EvaluationParameterCoverage {
  parameter_coverage_known: number;
  parameter_coverage_total: number;
}


export interface MetricDirections {
  directions: Record<string, 'higher_is_better' | 'lower_is_better'>;
}

/** One entry in the `metrics` array returned by
 *  `GET /api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics`. The backend
 *  prefixes fields with `metric_` because the wrapper also has a `task_id` /
 *  `dataset_id` for the leaderboard itself. */
export interface LeaderboardMetric {
  metric_id: string;
  metric_name: string;
  metric_direction: 'higher_is_better' | 'lower_is_better';
  created_at?: string;
}

export interface LeaderboardMetricsResponse {
  task_id: string;
  dataset_id: string;
  task_name: string;
  dataset_name: string;
  supports_harness: boolean;
  metrics: LeaderboardMetric[];
}

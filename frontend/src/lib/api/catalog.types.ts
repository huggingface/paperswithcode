export interface CatalogMutationEvent {
  actor_hf_subject?: string;
  editing_suspended?: boolean;
  paper_id?: number | null;
  id: string;
  actor_username: string | null;
  actor_role: "admin" | "contributor";
  operation: string;
  entity_type: string;
  entity_id: string;
  before: unknown;
  after: unknown;
  created_at: string;
  rollback_of_event_id: string | null;
  rollback_eligible?: boolean;
}

export interface CatalogAuditPage {
  events: CatalogMutationEvent[];
  next_cursor: string | null;
  unread_contributor_count?: number;
}

export interface Area {
  id: string;
  name: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

interface AreaWithTasks {
  id: string;
  name: string;
  description?: string;
  tasks: Task[];
}

export interface AreasWithTasks {
  results: AreaWithTasks[];
}

export interface ConferenceDeadline {
  type?: string;
  label?: string;
  deadline_at: string;
  timezone?: string;
}

export interface Conference {
  id: string;
  name: string;
  slug: string;
  short_name?: string;
  year?: number;
  url?: string;
  start_date?: string;
  end_date?: string;
  venue?: string;
  location?: string;
  description?: string;
  image_url?: string;
  image_credit?: string;
  hf_url?: string;
  paper_count?: number;
  tier?: string;
  tags?: string[];
  country?: string;
  city?: string;
  deadlines?: ConferenceDeadline[];
  created_at?: string;
  updated_at?: string;
}

export interface Conferences {
  count: number;
  results: Conference[];
}

export interface ConferenceDeadlines {
  count: number;
  results: Conference[];
}

interface ConferenceTaskSummary {
  id: string;
  name: string;
  slug?: string;
  paper_count: number;
}

interface ConferenceAreaWithTasks {
  id: string;
  name: string;
  description?: string;
  tasks: ConferenceTaskSummary[];
}

export interface ConferenceAreasWithTasks {
  conference: Conference;
  total_paper_count: number;
  oral_paper_count: number;
  spotlight_paper_count: number;
  outstanding_paper_count: number;
  best_paper_finalist_paper_count: number;
  results: ConferenceAreaWithTasks[];
}

/** Lightweight organization summary embedded in paper responses. */
export interface OrganizationSummary {
  id: string;
  name: string;
  slug: string;
  logo_url?: string | null;
  source: 'manual' | 'hf_org_papers' | 'curation' | 'openalex';
  added_by_hf_username?: string | null;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  hf_slug?: string | null;
  hf_url?: string | null;
  logo_url?: string | null;
  website_url?: string | null;
  github_url?: string | null;
  description?: string | null;
  paper_count?: number;
  is_featured: boolean;
  display_order?: number | null;
  organization_trending_score?: number | null;
  trending_rank?: number | null;
  top_trending_paper?: {
    id: string;
    arxiv_id?: string | null;
    title: string;
  } | null;
  first_paper_year?: number | null;
  latest_paper_year?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface Organizations {
  count: number;
  results: Organization[];
}

interface OrganizationContributionDay {
  date: string;
  paper_count: number;
}

export interface OrganizationContributions {
  start_date: string;
  end_date: string;
  total_count: number;
  results: OrganizationContributionDay[];
}

interface OrganizationAreaWithTasks {
  id: string;
  name: string;
  description?: string | null;
  tasks: ConferenceTaskSummary[];
}

export interface OrganizationAreasWithTasks {
  organization: Organization;
  total_paper_count: number;
  results: OrganizationAreaWithTasks[];
}

export interface Task {
  id: string;
  name: string;
  description?: string;
  research_trends?: string[];
  slug?: string;
  parent_id?: string;
  area_id?: string;
  level: number;
  paper_count?: number;
  image_url?: string;
  image_credit?: string;
  created_at?: string;
  updated_at?: string;
}

interface TrendingTask extends Task {
  recent_paper_count: number;
  baseline_paper_count: number;
  share_lift: number;
  trend_score: number;
}

interface TaskSubtaskBenchmarks {
  subtask_id: string;
  benchmarks: Dataset[];
}

export interface RecommendedFramework {
  id: string;
  framework_id: string;
  framework_slug: string;
  framework_name: string;
  url: string;
  owner?: string;
  name?: string;
  num_stars: number;
}

export type FrameworkPlatform = "gpu" | "cpu" | "apple";

export interface Framework {
  id: string;
  slug: string;
  name: string;
  organization_name?: string | null;
  description: string;
  when_to_use?: string | null;
  platforms: FrameworkPlatform[];
  github_url?: string | null;
  repository?: string | null;
  paper_count: number;
  docs_url?: string | null;
  introducing_paper_arxiv_id?: string | null;
}

interface FrameworkCategory {
  slug: string;
  name: string;
  description?: string | null;
  guide_url?: string | null;
  guide_label?: string | null;
  frameworks: Framework[];
}

interface FrameworkDomain {
  slug: string;
  name: string;
  description: string;
  categories: FrameworkCategory[];
}

/** Framework directory returned by `GET /frameworks/catalog`. */
export interface FrameworkCatalog {
  domains: FrameworkDomain[];
}

/** Bundled task-page payload returned by `GET /tasks/{id}/page`. Collapses the
 *  task-detail page's initial fan-out (detail, parents, sisters, recommended
 *  frameworks, children, direct benchmarks, and previews) into one request. */
export interface TaskPage {
  task: Task;
  area?: Area;
  parents: Task[];
  sisters: Task[];
  recommended_frameworks: RecommendedFramework[];
  children: Task[];
  benchmarks: Dataset[];
  subtask_benchmarks: TaskSubtaskBenchmarks[];
}

export interface TrendingTasksResponse {
  results: TrendingTask[];
  recent_days: number;
  baseline_days: number;
}

export interface BenchmarkTrendPoint {
  start_date: string;
  end_date: string;
  paper_count: number;
}

export interface TrendingBenchmark {
  id: string;
  name: string;
  slug?: string | null;
  full_name?: string | null;
  recent_paper_count: number;
  baseline_paper_count: number;
  all_time_paper_count: number;
  trend_score: number;
  support_weighted_score: number;
  rate_change?: number | null;
  latest_reported_on?: string | null;
  best_model_name?: string | null;
  best_paper_route?: string | null;
  best_paper_title?: string | null;
  best_code_url?: string | null;
  history: BenchmarkTrendPoint[];
}

export interface TrendingBenchmarksResponse {
  task_id: string;
  task_slug: string;
  signal: "evaluation_reports";
  recent_days: number;
  baseline_days: number;
  bucket_days: number;
  support_prior_papers: number;
  generated_on: string;
  results: TrendingBenchmark[];
}

export interface Method {
  id: string;
  name: string;
  slug?: string;
  full_name?: string;
  description?: string;
  area_id?: string;
  introduced_year?: number;
  source_paper_id?: string;
  source_url?: string;
  source_title?: string;
  code_snippet_url?: string;
  image_url?: string;
  image_credit?: string;
  collection_name?: string;
  collection_description?: string;
  collection_parent?: string;
  paper_count?: number;
  recent_paper_count?: number;
  baseline_paper_count?: number;
  /** Recent method mention velocity, normalized to papers per 30 days. */
  trend_score?: number;
  /** Recent usage velocity divided by the preceding baseline velocity. */
  rate_change?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface MethodIndexEntry {
  id: string;
  name: string;
  slug?: string;
  area_id?: string;
  introduced_year?: number;
  paper_count: number;
  trend_score: number;
}

export interface MethodIndex {
  count: number;
  results: MethodIndexEntry[];
}

export interface TrendingMethod {
  id: string;
  name: string;
  full_name?: string | null;
  slug?: string | null;
  area_id?: string | null;
  introduced_year?: number | null;
  recent_paper_count: number;
  baseline_paper_count: number;
  share_lift: number;
  trend_score: number;
}

export interface TrendingMethodsResponse {
  results: TrendingMethod[];
  recent_days: number;
  baseline_days: number;
}

export interface RelatedMethod {
  id: string;
  name: string;
  slug: string;
}

export interface RelatedMethods {
  results: RelatedMethod[];
}

export interface MethodTrendPoint {
  start_date: string;
  end_date: string;
  paper_count: number;
  eligible_paper_count?: number;
  processed_paper_count?: number;
  coverage_ratio?: number | null;
  coverage_status?: "pending" | "running" | "complete" | "failed" | "not_applicable";
  catalog_paper_count?: number;
  catalog_share?: number;
}

export interface MethodTrend {
  method_id: string;
  method_slug?: string | null;
  signal: "paper_method_links";
  recent_days: number;
  baseline_days: number;
  history_months: number;
  generated_on: string;
  recent_paper_count: number;
  baseline_paper_count: number;
  trend_score: number;
  rate_change?: number | null;
  history: MethodTrendPoint[];
  undated_paper_count?: number;
  history_complete?: boolean;
  comparison_complete: boolean;
  current_month_is_partial?: boolean;
}

interface IntroducingPaper {
  id: string;
  arxiv_id?: string | null;
  title: string;
  /** ISO date string (YYYY-MM-DD) of the introducing paper's publication date. */
  published?: string | null;
}

export interface Dataset {
  id: string;
  name: string;
  full_name?: string;
  description?: string;
  url?: string;
  hf_url?: string;
  slug?: string;
  parent_dataset_id?: string | null;
  paper_count?: number;
  supports_harness?: boolean;
  best_model_name?: string | null;
  best_paper_route?: string | null;
  best_paper_title?: string | null;
  best_code_url?: string | null;
  leaderboard_summary?: {
    task_id: string;
    task_slug?: string | null;
    metric: string;
    value: string | number;
    model_name: string;
    evaluation_id: string;
  } | null;
  introducing_paper_id?: string;
  introducing_paper_title?: string;
  paper_url?: string;
  introduced_year?: number;
  introduced_date?: string;
  created_at?: string;
  updated_at?: string;
  /** Optional embedded paper. Populated when the request asked for
   * `?include_paper=true`; saves a follow-up GET /papers/{id} round trip. */
  introducing_paper?: IntroducingPaper | null;
}

import type {
  Area,
  AreasWithTasks,
  CatalogAuditPage,
  CatalogMutationEvent,
  Conference,
  ConferenceAreasWithTasks,
  ConferenceDeadlines,
  Conferences,
  Dataset,
  FrameworkCatalog,
  Method,
  MethodIndex,
  MethodTrend,
  Organization,
  OrganizationAreasWithTasks,
  OrganizationContributions,
  Organizations,
  RelatedMethods,
  Task,
  TaskPage,
  TrendingBenchmarksResponse,
  TrendingMethodsResponse,
  TrendingTasksResponse,
} from "./catalog.types";
import type {
  LeaderboardMetric,
  LeaderboardMetricsResponse,
  MetricDirections,
} from "./evaluations.types";
import type { PaginatedResponse } from "./shared.types";
import type { ApiRequest } from "../apiTransport";
import { apiRequest } from "./request";

type QueryValue = string | number | boolean | undefined;

function endpoint(path: string, params?: Record<string, QueryValue>): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== "") searchParams.set(key, String(value));
  }
  const query = searchParams.toString();
  return `${path}${query ? `?${query}` : ""}`;
}

export class CatalogApi {
  constructor(private readonly request: ApiRequest) {}

  listAreas(params?: { page?: number; page_size?: number; q?: string; name?: string; ordering?: string }) {
    return this.request<PaginatedResponse<Area>>(endpoint("/areas/", params));
  }

  getArea(id: string): Promise<Area> {
    return this.request(`/areas/${id}`);
  }

  areasWithTasks(): Promise<AreasWithTasks> {
    return this.request("/areas/with-tasks/");
  }

  listTasks(params?: {
    page?: number;
    page_size?: number;
    q?: string;
    name?: string;
    area_id?: number;
    parent_id?: number;
    level?: number;
    ordering?: string;
  }) {
    return this.request<PaginatedResponse<Task>>(endpoint("/tasks/", params));
  }

  getTask(id: string): Promise<Task> {
    return this.request(`/tasks/${id}`);
  }

  topTasks(limit?: number): Promise<Task[]> {
    return this.request(endpoint("/tasks/top", { limit }));
  }

  trendingTasks(params?: {
    limit?: number;
    recent_days?: number;
    baseline_days?: number;
    level?: number;
    min_recent_papers?: number;
    min_baseline_papers?: number;
    min_share_lift?: number;
  }): Promise<TrendingTasksResponse> {
    return this.request(endpoint("/tasks/trending", params));
  }

  taskChildren(taskId: string, params?: { page?: number; page_size?: number }) {
    return this.request<PaginatedResponse<Task>>(endpoint(`/tasks/${taskId}/children`, params));
  }

  taskParents(taskId: string): Promise<Task[]> {
    return this.request(`/tasks/${taskId}/parents`);
  }

  taskPage(taskId: string, params?: { is_open?: boolean }): Promise<TaskPage> {
    return this.request(endpoint(`/tasks/${taskId}/page`, params));
  }

  trendingBenchmarks(taskId: string, params?: {
    limit?: number;
    recent_days?: number;
    baseline_days?: number;
    min_recent_papers?: number;
    include_descendants?: boolean;
    bucket_days?: number;
    history_buckets?: number;
    is_open?: boolean;
  }): Promise<TrendingBenchmarksResponse> {
    return this.request(endpoint(`/tasks/${encodeURIComponent(taskId)}/trending-benchmarks`, params));
  }

  frameworkCatalog(): Promise<FrameworkCatalog> {
    return this.request("/frameworks/");
  }

  listMethods(params?: {
    page?: number;
    page_size?: number;
    q?: string;
    name?: string;
    full_name?: string;
    introduced_year?: number;
    area_id?: number | string;
    exclude_id?: number | string;
    include_trends?: boolean;
    ordering?: string;
  }) {
    return this.request<PaginatedResponse<Method>>(endpoint("/methods/", params));
  }

  methodIndex(): Promise<MethodIndex> {
    return this.request("/methods/index/cards");
  }

  trendingMethods(params?: {
    limit?: number;
    recent_days?: number;
    baseline_days?: number;
    min_recent_papers?: number;
    min_baseline_papers?: number;
    min_share_lift?: number;
  }): Promise<TrendingMethodsResponse> {
    return this.request(endpoint("/methods/trending", params));
  }

  getMethod(id: string): Promise<Method> {
    return this.request(`/methods/${encodeURIComponent(id)}`);
  }

  relatedMethods(id: string): Promise<RelatedMethods> {
    return this.request(`/methods/${encodeURIComponent(id)}/related`);
  }

  methodTrend(id: string, params?: { recent_days?: number; baseline_days?: number; history_months?: number }): Promise<MethodTrend> {
    return this.request(endpoint(`/methods/${encodeURIComponent(id)}/trend`, params));
  }

  listDatasets(params?: {
    page?: number;
    page_size?: number;
    q?: string;
    name?: string;
    full_name?: string;
    task?: string;
    task_id?: number;
    include_descendants?: boolean;
    min_eval_count?: number;
    is_open?: boolean;
    ordering?: string;
  }) {
    const { task_id, ...rest } = params ?? {};
    return this.request<PaginatedResponse<Dataset>>(
      endpoint("/datasets/", { ...rest, task: rest.task ?? task_id }),
    );
  }

  getDataset(id: string): Promise<Dataset> {
    return this.request(`/datasets/${id}`);
  }

  getDatasetBySlug(
    slug: string,
    options?: { include_paper?: boolean; task?: string; is_open?: boolean },
  ): Promise<Dataset> {
    return this.request(endpoint(`/datasets/${slug}`, options));
  }

  async datasetTasks(datasetId: string): Promise<Task[]> {
    const response = await this.request<PaginatedResponse<Task>>(`/datasets/${datasetId}/tasks/`);
    return response.results;
  }

  async leaderboardMetrics(datasetId: string, taskId: string): Promise<LeaderboardMetric[]> {
    const response = await this.request<LeaderboardMetricsResponse>(
      `/datasets/${datasetId}/tasks/${taskId}/metrics`,
    );
    return response.metrics;
  }

  metricDirections(): Promise<MetricDirections> {
    return this.request("/metrics/directions");
  }

  conferences(): Promise<Conferences> {
    return this.request("/conferences/");
  }

  conferenceDeadlines(): Promise<ConferenceDeadlines> {
    return this.request("/conferences/deadlines");
  }

  getConference(slug: string): Promise<Conference> {
    return this.request(`/conferences/${slug}`);
  }

  conferenceAreasWithTasks(slug: string): Promise<ConferenceAreasWithTasks> {
    return this.request(`/conferences/${slug}/areas-with-tasks`);
  }

  organizations(featuredOnly = false): Promise<Organizations> {
    return this.request(`/organizations/${featuredOnly ? "?featured_only=true" : ""}`);
  }

  searchOrganizations(q: string, limit: number): Promise<Organizations> {
    return this.request(endpoint("/organizations/", { q, limit }));
  }

  organizationIndex(): Promise<Organizations> {
    return this.request("/organizations/index/cards");
  }

  getOrganization(slug: string): Promise<Organization> {
    return this.request(`/organizations/${slug}`);
  }

  organizationContributions(slug: string): Promise<OrganizationContributions> {
    return this.request(`/organizations/${slug}/contributions`);
  }

  organizationAreasWithTasks(slug: string): Promise<OrganizationAreasWithTasks> {
    return this.request(`/organizations/${slug}/areas-with-tasks`);
  }

  audit(cursor?: string): Promise<CatalogAuditPage> {
    return this.request(endpoint("/admin/catalog-audit", { cursor }));
  }

  acknowledgeAudit(): Promise<void> {
    return this.request("/admin/catalog-audit/acknowledge", { method: "POST" });
  }

  rollbackEvent(eventId: string): Promise<CatalogMutationEvent> {
    return this.request(`/admin/catalog-audit/${eventId}/rollback`, { method: "POST" });
  }
}

export const catalogApi = new CatalogApi(apiRequest);

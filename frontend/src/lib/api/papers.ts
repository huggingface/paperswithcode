import type {
  Author,
  Paper,
  PaperBucketCopyRequest,
  PaperBucketCopyResponse,
  PaperLookupResponse,
  PaperOrderBy,
  PaperReferenceQuery,
  PaperSearchMode,
  PaperSubmitPayload,
  PaperSubmitResponse,
  RelatedPaperRecommendation,
  TrendingPaper,
} from "./papers.types";
import type { PaginatedResponse, PaperSearchFeedPage, SearchPage } from "./shared.types";
import type { ApiRequest } from "../apiTransport";
import { paperCuration } from "./curation";
import { apiRequest } from "./request";

export interface ListPapersParams {
  page?: number;
  page_size?: number;
  search?: string;
  order_by?: PaperOrderBy;
  order_dir?: "asc" | "desc";
  start_date?: string;
  end_date?: string;
  conference?: string;
  task?: string;
  method?: string;
  latest_only?: boolean;
  include_resources?: boolean;
  has_code?: boolean;
  has_hf_artifacts?: boolean;
  framework?: string;
  repository?: string;
  /** Numeric author ID, exact author name, or @HF username. */
  author?: string;
}

export interface PaperFeedParams {
  page?: number;
  page_size?: number;
  order_by?: "trending" | "date_published" | "citation_count" | "title";
  order_dir?: "asc" | "desc";
  latest_only?: boolean;
  include_resources?: boolean;
  has_code?: boolean;
  has_hf_artifacts?: boolean;
  start_date?: string;
  end_date?: string;
}

export interface PaperSearchFeedParams {
  q: string;
  page?: number;
  page_size?: number;
  order_by?: "relevance" | "date_published" | "citation_count";
  start_date?: string;
  end_date?: string;
  has_code?: boolean;
  has_hf_artifacts?: boolean;
  mode?: PaperSearchMode;
}

function query(params?: object): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== "") searchParams.set(key, String(value));
  }
  const value = searchParams.toString();
  return value ? `?${value}` : "";
}

export class PapersApi {
  constructor(private readonly request: ApiRequest) {}

  list(params?: ListPapersParams): Promise<PaginatedResponse<Paper>> {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params ?? {})) {
      if (value !== undefined && value !== "") searchParams.set(key, String(value));
    }
    const query = searchParams.toString();
    return this.request<PaginatedResponse<Paper>>(`/papers/${query ? `?${query}` : ""}`, {
      cache: "no-cache",
    });
  }

  search(
    query: string,
    page = 1,
    pageSize = 10,
    mode?: PaperSearchMode,
    signal?: AbortSignal,
    dateRange?: { start_date?: string; end_date?: string },
  ): Promise<SearchPage<Paper>> {
    const searchParams = new URLSearchParams({
      q: query,
      page: page.toString(),
      page_size: pageSize.toString(),
    });
    if (mode) searchParams.set("mode", mode);
    if (dateRange?.start_date) searchParams.set("start_date", dateRange.start_date);
    if (dateRange?.end_date) searchParams.set("end_date", dateRange.end_date);
    return this.request<SearchPage<Paper>>(
      `/papers/search?${searchParams.toString()}`,
      { signal },
    );
  }

  searchFeed(params: PaperSearchFeedParams): Promise<PaperSearchFeedPage<Paper>> {
    return this.request(`/papers/search/feed${query(params)}`, { cache: "no-cache" });
  }

  get(id: string, includeResources = true): Promise<Paper> {
    const query = includeResources ? "?include_resources=true" : "";
    return this.request<Paper>(`/papers/${id}${query}`);
  }

  getByArxivId(arxivId: string, includeResources = true): Promise<Paper> {
    const query = includeResources ? "?include_resources=true" : "";
    return this.request<Paper>(`/papers/arxiv/${arxivId}${query}`);
  }

  /** Match bibliography entries to catalog papers in one round trip. */
  lookup(references: PaperReferenceQuery[]): Promise<PaperLookupResponse> {
    return this.request<PaperLookupResponse>("/papers/lookup", {
      method: "POST",
      body: JSON.stringify({ references }),
    });
  }

  related(id: string, limit = 4): Promise<RelatedPaperRecommendation[]> {
    return this.request<RelatedPaperRecommendation[]>(
      `/papers/${encodeURIComponent(id)}/related?limit=${limit}`,
    );
  }

  versions(arxivId: string): Promise<Paper[]> {
    return this.request(`/papers/arxiv/${arxivId}/versions`);
  }

  indexFromArxiv(arxivId: string): Promise<Paper> {
    return this.request<Paper>(`/papers/index/${arxivId}`, { method: "POST" });
  }

  submit(payload: PaperSubmitPayload): Promise<PaperSubmitResponse> {
    return this.request<PaperSubmitResponse>("/papers/submit", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  copyToBucket(paperId: string, payload: PaperBucketCopyRequest): Promise<PaperBucketCopyResponse> {
    return this.request(`/papers/${encodeURIComponent(paperId)}/copy-to-bucket`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  trending(params?: { limit?: number; max_age_days?: number; min_velocity?: number }): Promise<TrendingPaper[]> {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params ?? {})) {
      if (value !== undefined) searchParams.set(key, String(value));
    }
    const query = searchParams.toString();
    return this.request<TrendingPaper[]>(`/papers/trending${query ? `?${query}` : ""}`, {
      cache: "no-store",
    });
  }

  forTask(
    taskId: string,
    params?: PaperFeedParams & { repository_limit?: number },
  ): Promise<PaginatedResponse<Paper>> {
    return this.request(`/tasks/${taskId}/papers${query(params)}`);
  }

  forMethod(
    methodId: string,
    params?: PaperFeedParams & { repository_limit?: number },
  ): Promise<PaginatedResponse<Paper>> {
    return this.request(`/methods/${encodeURIComponent(methodId)}/papers${query(params)}`);
  }

  forConference(
    slug: string,
    params?: PaperFeedParams & {
      task?: string;
      presentation?: "oral" | "spotlight" | "outstanding" | "best_paper_finalist";
    },
  ): Promise<PaginatedResponse<Paper>> {
    return this.request(`/conferences/${slug}/papers${query(params)}`);
  }

  forOrganization(
    slug: string,
    params?: PaperFeedParams & { task?: string },
  ): Promise<PaginatedResponse<Paper>> {
    return this.request(`/organizations/${slug}/papers${query(params)}`);
  }

  getAuthor(id: string): Promise<Author> {
    return this.request(`/authors/${id}`);
  }

  primeCurationState(paperId: string, force = false) {
    return paperCuration.primePaper(paperId, force);
  }

  freshAuthMutationDraft() {
    return paperCuration.freshAuthMutationDraft();
  }

  resumeFreshAuthMutation<T>(): Promise<T> {
    return paperCuration.resumeFreshAuthMutation<T>();
  }

  updateTasks(paperId: string, taskIds: number[]): Promise<Paper> {
    const query = new URLSearchParams(taskIds.map((id) => ["task_ids", String(id)])).toString();
    return paperCuration.mutatePaper(paperId, "tasks", taskIds, `/papers/${paperId}/tasks?${query}`, {
      method: "PUT",
    });
  }

  updateMethods(paperId: string, methodIds: number[]): Promise<Paper> {
    const query = new URLSearchParams(methodIds.map((id) => ["method_ids", String(id)])).toString();
    return paperCuration.mutatePaper(paperId, "methods", methodIds, `/papers/${paperId}/methods?${query}`, {
      method: "PUT",
    });
  }

  updateOrganizations(paperId: string, organizationIds: number[]): Promise<Paper> {
    const query = new URLSearchParams(
      organizationIds.map((id) => ["organization_ids", String(id)]),
    ).toString();
    return paperCuration.mutatePaper(
      paperId,
      "organizations",
      organizationIds,
      `/papers/${paperId}/organizations?${query}`,
      { method: "PUT" },
    );
  }

  updateRepositories(
    paperId: string,
    repositories: Array<{ url: string; is_official: boolean }>,
  ): Promise<Paper> {
    return paperCuration.mutatePaper(
      paperId,
      "repositories",
      repositories,
      `/papers/${paperId}/repositories`,
      { method: "PUT", body: JSON.stringify({ repositories }) },
    );
  }

  updateProjectPages(
    paperId: string,
    projectPages: Array<{ url: string; is_official: boolean }>,
  ): Promise<Paper> {
    return paperCuration.mutatePaper(
      paperId,
      "project_pages",
      projectPages,
      `/papers/${paperId}/project-pages`,
      { method: "PUT", body: JSON.stringify({ project_pages: projectPages }) },
    );
  }

  updateXThreads(paperId: string, xThreads: string[]): Promise<Paper> {
    return paperCuration.mutatePaper(
      paperId,
      "x_threads",
      xThreads,
      `/papers/${paperId}/x-threads`,
      { method: "PUT", body: JSON.stringify({ x_threads: xThreads }) },
    );
  }

  updateSourceUrl(paperId: string, sourceUrl: string): Promise<Paper> {
    return paperCuration.mutatePaper(
      paperId,
      "source_url",
      sourceUrl,
      `/papers/${paperId}/source-url`,
      { method: "PUT", body: JSON.stringify({ source_url: sourceUrl }) },
    );
  }

  updateHfArtifacts(
    paperId: string,
    artifacts: { hf_models: string[]; hf_datasets: string[]; hf_spaces: string[] },
  ): Promise<Paper> {
    return paperCuration.mutatePaper(
      paperId,
      "hf_artifacts",
      artifacts,
      `/papers/${paperId}/hf-artifacts`,
      { method: "PUT", body: JSON.stringify(artifacts) },
    );
  }
}

export const papersApi = new PapersApi(apiRequest);

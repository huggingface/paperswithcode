import type { Evaluation, EvaluationParameterCoverage } from "./evaluations.types";
import type { PaginatedResponse } from "./shared.types";
import type { ApiRequest } from "../apiTransport";
import { paperCuration } from "./curation";
import { apiRequest } from "./request";

export interface EvaluationQuery {
  page?: number;
  page_size?: number;
  q?: string;
  paper_id?: number;
  task_id?: number;
  include_descendants?: boolean;
  dataset_id?: number;
  best_metric?: string;
  is_open?: boolean;
  external?: boolean;
  max_parameters_exclusive?: number;
  ordering?: string;
}

export type EvaluationWrite = {
  paper_id?: number;
  task_id?: number;
  dataset_id?: number;
  model_name?: string;
  harness?: string | null;
  methodology?: string;
  metrics?: Record<string, string | number>;
  uses_additional_data?: boolean;
  is_open?: boolean;
  best_rank?: number;
  best_metric?: string;
  evaluated_on?: string;
  external_source_url?: string;
  source_url?: string | null;
  num_parameters?: number | null;
  hf_model_url?: string | null;
};

export class EvaluationsApi {
  constructor(private readonly request: ApiRequest) {}

  list(params: EvaluationQuery = {}): Promise<PaginatedResponse<Evaluation> & EvaluationParameterCoverage> {
    const query = new URLSearchParams(
      Object.entries(params)
        .filter((entry): entry is [string, string | number] => entry[1] !== undefined)
        .map(([key, value]) => [key, String(value)]),
    ).toString();
    return this.request(`/evaluations/${query ? `?${query}` : ""}`, { cache: "no-store" });
  }

  get(id: string): Promise<Evaluation> {
    return this.request(`/evaluations/${id}`);
  }

  async byPaper(paperId: string): Promise<Evaluation[]> {
    return this.allPages({
      paper_id: Number(paperId),
      ordering: "-benchmark_popularity",
    });
  }

  async byDataset(datasetId: string, bestMetric?: string): Promise<Evaluation[]> {
    return this.allPages({
      dataset_id: Number(datasetId),
      best_metric: bestMetric,
      ordering: "best_rank",
    });
  }

  async byLeaderboard(
    datasetId: string,
    taskId: string,
    options: Pick<EvaluationQuery, "is_open" | "max_parameters_exclusive"> = {},
  ): Promise<Evaluation[]> {
    return this.allPages({
      dataset_id: Number(datasetId),
      task_id: Number(taskId),
      ordering: "best_rank",
      ...options,
    });
  }

  create(data: EvaluationWrite & { paper_id: number; task_id: number; dataset_id: number; metrics: Record<string, string | number> }): Promise<Evaluation> {
    return this.request("/evaluations/", { method: "POST", body: JSON.stringify(data) });
  }

  update(id: string, data: EvaluationWrite): Promise<Evaluation> {
    return this.request(`/evaluations/${id}`, { method: "PUT", body: JSON.stringify(data) });
  }

  delete(id: string): Promise<void> {
    return this.request(`/evaluations/${id}`, { method: "DELETE" });
  }

  primeCurationState(paperId: string, force = false) {
    return paperCuration.primeEvaluations(paperId, force);
  }

  batch(
    paperId: number,
    operations: Array<{
      operation: "create" | "update" | "delete";
      evaluation_id?: number;
      payload?: Record<string, unknown>;
    }>,
  ): Promise<{ event_id: string }> {
    return paperCuration.mutateEvaluations(paperId, operations, "/evaluations/batch", {
      method: "POST",
      body: JSON.stringify({ paper_id: paperId, operations }),
    });
  }

  private async allPages(params: EvaluationQuery): Promise<Evaluation[]> {
    const pageSize = 100;
    const firstPage = await this.list({ ...params, page_size: pageSize });
    if (!firstPage.next_page) return firstPage.results;
    // The first page reports the total, so fetch the rest concurrently.
    const pageCount = Math.ceil(firstPage.count / pageSize);
    const remaining = await Promise.all(
      Array.from({ length: pageCount - 1 }, (_, index) =>
        this.list({ ...params, page: index + 2, page_size: pageSize }),
      ),
    );
    return [firstPage, ...remaining].flatMap((page) => page.results);
  }
}

export const evaluationsApi = new EvaluationsApi(apiRequest);

import type { CodexJobFilters, CodexPaperJob, CodexPaperJobsResponse } from "./codex.types";
export type * from "./codex.types";
import type { ApiRequest } from "../apiTransport";
import { apiUrl } from "../apiUrl";
import { apiRequest } from "./request";

/** Codex jobs an admin can start from a paper page. */
export type CodexPaperJobKind = "add-evals" | "enrich-paper";

export const AWAITING_MARKDOWN_MESSAGE =
  "No paper text was available yet. This job starts again automatically within an hour of the paper's Markdown being extracted.";

const CURATION_JOBS = "/admin/codex-curation/jobs";

export class CodexApi {
  constructor(private readonly request: ApiRequest) {}

  startPaperJob(kind: CodexPaperJobKind, paperId: number): Promise<CodexPaperJob> {
    return this.request(`/admin/codex-${kind}/jobs`, {
      method: "POST",
      body: JSON.stringify({ paper_id: paperId }),
    });
  }

  getPaperJob(kind: CodexPaperJobKind, jobId: string): Promise<CodexPaperJob> {
    return this.request(`/admin/codex-${kind}/jobs/${jobId}`);
  }

  cancelPaperJob(kind: CodexPaperJobKind, jobId: string): Promise<CodexPaperJob> {
    return this.request(`/admin/codex-${kind}/jobs/${jobId}`, { method: "DELETE" });
  }

  listJobs(limit = 100, filters: CodexJobFilters = {}): Promise<CodexPaperJobsResponse> {
    const query = new URLSearchParams({ limit: String(limit) });
    Object.entries(filters).forEach(([key, value]) => { if (value) query.set(key, value); });
    return this.request(`${CURATION_JOBS}?${query}`, { cache: "no-store" });
  }

  retryJob(jobId: string): Promise<CodexPaperJob> {
    return this.request(`${CURATION_JOBS}/${jobId}/retry`, { method: "POST" });
  }

  cancelJob(jobId: string): Promise<CodexPaperJob> {
    return this.request(`${CURATION_JOBS}/${jobId}`, { method: "DELETE" });
  }

  async retryTrace(jobId: string): Promise<void> {
    await this.request(`${CURATION_JOBS}/${jobId}/retry-trace`, { method: "POST" });
  }

  async setScheduler(action: "pause" | "resume"): Promise<void> {
    await this.request(`${CURATION_JOBS}/scheduler/${action}`, { method: "POST" });
  }

  async promoteBenchmarkCandidate(
    candidateId: string,
    payload: { dataset_id: number; task_id: number; best_metric: string },
  ): Promise<void> {
    await this.request(`${CURATION_JOBS}/benchmark-candidates/${candidateId}/promote`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async rollbackBenchmarkCandidate(candidateId: string): Promise<void> {
    await this.request(`${CURATION_JOBS}/benchmark-candidates/${candidateId}/rollback`, {
      method: "POST",
    });
  }

  /** Browser link to a job's authenticated trace manifest. */
  traceUrl(jobId: string): string {
    return apiUrl(`/api/v1${CURATION_JOBS}/${jobId}/trace`);
  }
}

export const codexApi = new CodexApi(apiRequest);

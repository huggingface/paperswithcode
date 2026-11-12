import type {
  AutonomousOperationsResponse,
  CronJobsResponse,
  PaperMarkdownJobsResponse,
  XPostRequestStatus,
} from "./operations.types";
export type * from "./operations.types";
import type { ApiRequest } from "../apiTransport";
import { apiRequest } from "./request";

export class OperationsApi {
  constructor(private readonly request: ApiRequest) {}

  getXPostRequest(paperId: number): Promise<XPostRequestStatus> {
    return this.request(`/admin/papers/${paperId}/x-post-request`, { cache: "no-store" });
  }

  setXPostRequest(paperId: number, requested: boolean): Promise<XPostRequestStatus> {
    return this.request(`/admin/papers/${paperId}/x-post-request`, {
      method: requested ? "POST" : "DELETE",
    });
  }

  getCronStatus(forceRefresh = false): Promise<CronJobsResponse> {
    const query = forceRefresh ? "?force_refresh=true" : "";
    return this.request(`/cron/status${query}`, { cache: "no-store" });
  }

  getPaperMarkdownJobs(): Promise<PaperMarkdownJobsResponse> {
    return this.request("/cron/paper-markdown-jobs", { cache: "no-store" });
  }

  getAutonomousOperations(): Promise<AutonomousOperationsResponse> {
    return this.request("/admin/autonomous-operations", { cache: "no-store" });
  }

  setAutonomousManualMode(
    enabled: boolean,
    expectedRevision: number,
    confirmation: string,
  ): Promise<AutonomousOperationsResponse> {
    return this.request("/admin/autonomous-operations/manual-mode", {
      method: "PATCH",
      body: JSON.stringify({
        enabled,
        expected_revision: expectedRevision,
        confirmation,
      }),
    });
  }

  setAutonomousOperator(
    operator: string,
    enabled: boolean,
    expectedRevision: number,
    confirmation: string,
  ): Promise<AutonomousOperationsResponse> {
    return this.request(`/admin/autonomous-operations/operators/${operator}`, {
      method: "PATCH",
      body: JSON.stringify({
        enabled,
        expected_revision: expectedRevision,
        confirmation,
      }),
    });
  }

  qualifyAutonomousChatBaseline(
    sha: string,
    expectedRevision: number,
    confirmation: string,
  ): Promise<AutonomousOperationsResponse> {
    return this.request("/admin/autonomous-operations/chat-baseline", {
      method: "POST",
      body: JSON.stringify({
        sha,
        expected_revision: expectedRevision,
        confirmation,
      }),
    });
  }
}

export const operationsApi = new OperationsApi(apiRequest);

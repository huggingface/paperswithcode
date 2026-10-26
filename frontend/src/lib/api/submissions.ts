import type {
  PendingEditStatus,
  PendingEditType,
  PendingPaperEdit,
  PendingPaperEditSubmitPayload,
  PendingPaperEditsResponse,
} from "../pendingEdits";
import type { ApiRequest } from "../apiTransport";
import {
  parsePendingPaperEdit,
  parsePendingPaperEditsResponse,
} from "../pendingEdits";
import { apiRequest } from "./request";

export class SubmissionsApi {
  constructor(private readonly request: ApiRequest) {}

  async submit(payload: PendingPaperEditSubmitPayload): Promise<PendingPaperEdit> {
    return parsePendingPaperEdit(await this.request<unknown>("/me/paper-edits", {
      method: "POST",
      body: JSON.stringify(payload),
    }));
  }

  list(params?: {
    status?: PendingEditStatus;
    edit_type?: PendingEditType;
    paper_id?: number;
    reviewed_by_kind?: "human" | "codex" | "auto";
    limit?: number;
    offset?: number;
  }): Promise<PendingPaperEditsResponse> {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params ?? {})) {
      if (value !== undefined) searchParams.set(key, String(value));
    }
    const query = searchParams.toString();
    return this.request<unknown>(`/admin/paper-edits${query ? `?${query}` : ""}`)
      .then(parsePendingPaperEditsResponse);
  }

  revertAutoApproved(
    hfSubject: string,
    body: { since_hours?: number; suspend?: boolean; reason?: string } = {},
  ): Promise<{ reverted: number; skipped: Array<{ event_id: string; reason: string }> }> {
    return this.request(`/admin/submitters/${encodeURIComponent(hfSubject)}/revert-auto-approved`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async get(id: number): Promise<PendingPaperEdit> {
    return parsePendingPaperEdit(await this.request<unknown>(`/admin/paper-edits/${id}`));
  }

  async approve(
    id: number,
    body: { admin_note?: string; user_review_reason?: string; resolved_payload?: Record<string, unknown> } = {},
  ): Promise<PendingPaperEdit> {
    return parsePendingPaperEdit(await this.request<unknown>(`/admin/paper-edits/${id}/approve`, {
      method: "POST",
      body: JSON.stringify(body),
    }));
  }

  async reject(
    id: number,
    body: { admin_note?: string; user_review_reason?: string } = {},
  ): Promise<PendingPaperEdit> {
    return parsePendingPaperEdit(await this.request<unknown>(`/admin/paper-edits/${id}/reject`, {
      method: "POST",
      body: JSON.stringify(body),
    }));
  }
}

export const submissionsApi = new SubmissionsApi(apiRequest);

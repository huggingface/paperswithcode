import type { OrganizationContributions } from "./catalog.types";
import { apiResponse } from "./request";

export interface ProfileResponse {
  username: string;
  redirected_from_alias: boolean;
  calendar: OrganizationContributions;
  is_owner: boolean;
  submissions: Array<{
    id: number;
    edit_type: string;
    status: string;
    proposed_payload: Record<string, unknown>;
    applied_payload?: Record<string, unknown> | null;
    review_reason?: string | null;
    created_at: string;
  }>;
}

export const profilesApi = {
  async get(username: string): Promise<ProfileResponse> {
    const response = await apiResponse(`/profiles/${encodeURIComponent(username)}`);
    const data = await response.json() as ProfileResponse;
    if (!response.redirected) return data;
    const canonical = decodeURIComponent(
      new URL(response.url).pathname.split("/").pop() || data.username,
    );
    return { ...data, username: canonical, redirected_from_alias: true };
  },
};

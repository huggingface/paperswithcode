import { apiRequest } from "./request";

export const paperEditsApi = {
  authorization: (id: string) => apiRequest<{ paper_id: number; title: string; user_code: string; approved: boolean; expires_at: string }>(`/paper-edit-authorizations/${encodeURIComponent(id)}`),
  approve: (id: string) => apiRequest<{ status: string; expires_at: string }>(`/paper-edit-authorizations/${encodeURIComponent(id)}/approve`, { method: "POST" }),
  digest: (day: string, page: number) => apiRequest<{ day: string; edits: number; contributors: number; papers: number; rows: { paper_id: number; actor_username: string | null; edits: number }[]; has_more: boolean }>(`/admin/paper-edit-digest?day=${day}&page=${page}`),
  suspend: (hfSubject: string, suspended: boolean) => apiRequest(`/admin/paper-edit-suspension`, { method: "POST", body: JSON.stringify({ hf_subject: hfSubject, suspended }) }),
};

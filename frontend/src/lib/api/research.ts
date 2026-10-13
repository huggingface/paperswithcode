import { apiRequest } from './request';

export type FollowKind = 'task' | 'method' | 'benchmark' | 'author' | 'organization';
export interface ResearchFollow {
  kind: FollowKind;
  entity_id: number;
  name: string;
  url: string;
  created_at: string;
}
export interface ResearchEmail {
  enabled: boolean;
  email: string | null;
  suppressed: boolean;
  delivery_ready: boolean;
}
export interface ResearchEntry {
  paper_key: string;
  title: string;
  url: string;
  summary: string;
  published: string;
  reasons: string[];
  scores: { benchmark: string; model: string | null; metrics: Record<string, unknown> }[];
}
export const researchApi = {
  follows: () => apiRequest<ResearchFollow[]>('/me/follows'),
  setFollow: (kind: FollowKind, id: string | number, enabled: boolean) =>
    apiRequest<void>(`/me/follows/${kind}/${id}`, { method: enabled ? 'PUT' : 'DELETE' }),
  following: (offset = 0) => apiRequest<ResearchEntry[]>(`/me/following?offset=${offset}&limit=40`),
  email: () => apiRequest<ResearchEmail>('/me/research-email'),
  setEmail: (enabled: boolean) => apiRequest<ResearchEmail>('/me/research-email', {
    method: 'PUT', body: JSON.stringify({ enabled }),
  }),
};

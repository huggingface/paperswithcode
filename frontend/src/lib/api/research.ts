import type { Paper } from './papers.types';
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
  paper: Paper;
  paper_key: string;
  title: string;
  url: string;
  summary: string;
  published: string;
  reasons: string[];
  scores: { benchmark: string; model: string | null; metrics: Record<string, unknown> }[];
}
export interface FollowingFilters {
  startDate?: string;
  endDate?: string;
  hasCode?: boolean;
  hasHfArtifacts?: boolean;
}
export const researchApi = {
  follows: () => apiRequest<ResearchFollow[]>('/me/follows'),
  setFollow: (kind: FollowKind, id: string | number, enabled: boolean) =>
    apiRequest<void>(`/me/follows/${kind}/${id}`, { method: enabled ? 'PUT' : 'DELETE' }),
  following: (offset = 0, filters: FollowingFilters = {}) => {
    const params = new URLSearchParams({ offset: String(offset), limit: '40' });
    if (filters.startDate) params.set('start_date', filters.startDate);
    if (filters.endDate) params.set('end_date', filters.endDate);
    if (!filters.startDate && !filters.endDate) params.set('all_time', 'true');
    if (filters.hasCode) params.set('has_code', 'true');
    if (filters.hasHfArtifacts) params.set('has_hf_artifacts', 'true');
    return apiRequest<ResearchEntry[]>(`/me/following?${params}`);
  },
  email: () => apiRequest<ResearchEmail>('/me/research-email'),
  setEmail: (enabled: boolean) => apiRequest<ResearchEmail>('/me/research-email', {
    method: 'PUT', body: JSON.stringify({ enabled }),
  }),
};

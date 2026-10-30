import type { Paper } from './papers.types';
import { apiRequest } from './request';

export type FollowKind = 'task' | 'method' | 'benchmark' | 'author' | 'organization';
export interface ResearchFollow {
  kind: FollowKind;
  entity_id: number;
  name: string;
  url: string;
  created_at: string;
  /** An author's face or an organization's logo. */
  image_url?: string | null;
}
export interface FollowSuggestion {
  entity_id: number;
  name: string;
  url: string;
  image_url: string | null;
}
export interface FollowSuggestions {
  authors: FollowSuggestion[];
  organizations: FollowSuggestion[];
}
export interface ResearchTopicSuggestion {
  kind: FollowKind;
  entity_id: number;
  name: string;
  url: string;
}
export interface ResearchTopic {
  text: string;
  /** Few-word summary of a long description; null for short ones. */
  label: string | null;
  set_at: string | null;
  /** pending/running while the last 90 days and older matches are judged. */
  status: 'pending' | 'running' | 'done' | 'failed';
  judged: number;
  total: number | null;
  suggestions: ResearchTopicSuggestion[];
}
export const TOPIC_MAX_LENGTH = 300;
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
  topicOnly?: boolean;
}
export const researchApi = {
  follows: () => apiRequest<ResearchFollow[]>('/me/follows'),
  followSuggestions: () => apiRequest<FollowSuggestions>('/research/follow-suggestions'),
  setFollow: (kind: FollowKind, id: string | number, enabled: boolean) =>
    apiRequest<void>(`/me/follows/${kind}/${id}`, { method: enabled ? 'PUT' : 'DELETE' }),
  following: (offset = 0, filters: FollowingFilters = {}) => {
    const params = new URLSearchParams({ offset: String(offset), limit: '40' });
    if (filters.startDate) params.set('start_date', filters.startDate);
    if (filters.endDate) params.set('end_date', filters.endDate);
    if (!filters.startDate && !filters.endDate) params.set('all_time', 'true');
    if (filters.topicOnly) params.set('topic_only', 'true');
    return apiRequest<ResearchEntry[]>(`/me/following?${params}`);
  },
  topic: () => apiRequest<ResearchTopic | null>('/me/topic'),
  setTopic: (text: string) => apiRequest<ResearchTopic>('/me/topic', {
    method: 'PUT', body: JSON.stringify({ text }),
  }),
  clearTopic: () => apiRequest<void>('/me/topic', { method: 'DELETE' }),
  email: () => apiRequest<ResearchEmail>('/me/research-email'),
  setEmail: (enabled: boolean) => apiRequest<ResearchEmail>('/me/research-email', {
    method: 'PUT', body: JSON.stringify({ enabled }),
  }),
};

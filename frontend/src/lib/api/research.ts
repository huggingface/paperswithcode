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
  /** A subtask's parent task slug, for its icon. */
  parent_slug?: string | null;
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
  id: number;
  text: string;
  /** Few-word summary of a long description; null for short ones. */
  label: string | null;
  set_at: string | null;
  /** pending/running while the last 90 days and older matches are judged. */
  status: 'pending' | 'running' | 'done' | 'failed';
  judged: number;
  total: number | null;
  suggestions: ResearchTopicSuggestion[];
  /** Public topics are listed with their creator's HF username; only the creator may change it. */
  is_public: boolean;
  is_creator: boolean;
  /** Who made a public topic the account follows from someone else; null for its own. */
  creator?: TopicPerson | null;
}
/** A Hugging Face account shown on a public topic. */
export interface TopicPerson {
  username: string;
  avatar_url: string;
}
/** A topic page header: what it matches, who made it, who follows it. */
export interface PublicTopic {
  id: number;
  text: string;
  label: string | null;
  status: ResearchTopic['status'];
  creator: TopicPerson | null;
  is_public: boolean;
  /** False while the topic has few followers or an admin hid it. */
  indexable: boolean;
  followers: number;
  /** Followers who show their avatar, creator excluded, at most eight. */
  follower_avatars: TopicPerson[];
  following: boolean;
  is_creator: boolean;
}
/** A popular public topic offered on the homepage. */
export interface TopicBubble {
  id: number;
  text: string;
  label: string | null;
  creator: TopicPerson | null;
  followers: number;
}
export type TopicPaperOrder = 'trending' | 'newest';
export const TOPIC_PAPERS_PAGE_SIZE = 20;
export const TOPIC_MAX_LENGTH = 300;
/** How many topics an account may follow. */
export const TOPIC_LIMIT = 10;
export interface ResearchEmail {
  enabled: boolean;
  email: string | null;
  suppressed: boolean;
  delivery_ready: boolean;
  /** Whether the account's avatar may appear on public topics it follows. */
  show_as_follower: boolean;
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
  /** When the paper joined the catalog. */
  added_at?: string | null;
}
export interface FollowingFilters {
  startDate?: string;
  endDate?: string;
  /** Only papers matching any followed topic. */
  topicOnly?: boolean;
  /** Only papers matching any of these topics or follows. */
  topicIds?: number[];
  /** Follows as `<kind>:<entity_id>`. */
  follows?: string[];
  /** Only papers added after this time, newest first, in place of the date window. */
  addedAfter?: string;
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
    filters.topicIds?.forEach(id => params.append('topic_id', String(id)));
    filters.follows?.forEach(follow => params.append('follow', follow));
    if (filters.addedAfter) params.set('added_after', filters.addedAfter);
    return apiRequest<ResearchEntry[]>(`/me/following?${params}`);
  },
  /** Following-feed papers added after `since`, at most 100. */
  followingNewCount: (since: string) =>
    apiRequest<{ count: number }>(`/me/following/new-count?${new URLSearchParams({ since })}`),
  topics: () => apiRequest<ResearchTopic[]>('/me/topics'),
  addTopic: (text: string) => apiRequest<ResearchTopic>('/me/topics', {
    method: 'POST', body: JSON.stringify({ text }),
  }),
  updateTopic: (id: number, text: string) => apiRequest<ResearchTopic>(`/me/topics/${id}`, {
    method: 'PUT', body: JSON.stringify({ text }),
  }),
  removeTopic: (id: number) => apiRequest<void>(`/me/topics/${id}`, { method: 'DELETE' }),
  reorderTopics: (ids: number[]) => apiRequest<ResearchTopic[]>('/me/topics/order', {
    method: 'PUT', body: JSON.stringify({ topic_ids: ids }),
  }),
  followTopic: (id: number) => apiRequest<ResearchTopic>(`/me/topics/${id}/follow`, { method: 'POST' }),
  setTopicPublic: (id: number, isPublic: boolean) => apiRequest<ResearchTopic>(`/me/topics/${id}`, {
    method: 'PATCH', body: JSON.stringify({ is_public: isPublic }),
  }),
  setShowAsFollower: (show: boolean) => apiRequest<void>('/me/topic-follower-visibility', {
    method: 'PUT', body: JSON.stringify({ show_as_follower: show }),
  }),
  publicTopic: (id: number) => apiRequest<PublicTopic>(`/research/topics/${id}`),
  topicPapers: (id: number, order: TopicPaperOrder, offset = 0, range: { startDate?: string; endDate?: string } = {}) => {
    const params = new URLSearchParams({ order, offset: String(offset), limit: String(TOPIC_PAPERS_PAGE_SIZE) });
    if (range.startDate) params.set('start_date', range.startDate);
    if (range.endDate) params.set('end_date', range.endDate);
    return apiRequest<Paper[]>(`/research/topics/${id}/papers?${params}`);
  },
  featuredTopics: () => apiRequest<TopicBubble[]>('/research/topics/featured'),
  /** Catalog tasks, methods and benchmarks a topic with this text would duplicate. */
  topicMatches: (text: string) =>
    apiRequest<ResearchTopicSuggestion[]>(`/research/topic-matches?${new URLSearchParams({ text })}`),
  email: () => apiRequest<ResearchEmail>('/me/research-email'),
  setEmail: (enabled: boolean) => apiRequest<ResearchEmail>('/me/research-email', {
    method: 'PUT', body: JSON.stringify({ enabled }),
  }),
};

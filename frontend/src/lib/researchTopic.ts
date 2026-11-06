import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { researchApi, type FollowKind, type ResearchTopic } from '@/lib/api/research';
import { researchQueryKeys } from '@/lib/api/queryKeys';
import { useOptionalAuth } from '@/lib/authContext';

/** Refreshes what a follow or topic change affects. */
function invalidateResearch(client: QueryClient, subject: string | undefined, { follows }: { follows: boolean }) {
  return Promise.all([
    follows && client.invalidateQueries({ queryKey: researchQueryKeys.follows(subject) }),
    client.invalidateQueries({ queryKey: researchQueryKeys.feed(subject) }),
    // Following something turns the weekly email on by default.
    client.invalidateQueries({ queryKey: researchQueryKeys.email(subject) }),
  ]);
}

/** What the signed-in account follows. */
export function useResearchFollows(enabled = true) {
  const user = useOptionalAuth()?.user;
  return useQuery({
    queryKey: researchQueryKeys.follows(user?.hf_subject),
    queryFn: researchApi.follows,
    enabled: enabled && !!user,
  });
}

export interface FollowChange {
  kind: FollowKind;
  entityId: string | number;
  follow: boolean;
}

/** Follows or unfollows one entity. `onChanged` runs before the refreshed follows arrive;
 * with `awaitRefresh` the mutation stays pending until they do. */
export function useSetFollow<Change extends FollowChange = FollowChange>(
  { onChanged, awaitRefresh = false }: { onChanged?: (change: Change) => void; awaitRefresh?: boolean } = {},
) {
  const user = useOptionalAuth()?.user;
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, entityId, follow }: Change) => researchApi.setFollow(kind, entityId, follow),
    onSuccess: async (_, change) => {
      onChanged?.(change);
      const refresh = invalidateResearch(client, user?.hf_subject, { follows: true });
      if (awaitRefresh) await refresh;
    },
  });
}

export const isTopicBuilding = (topic: ResearchTopic) => topic.status === 'pending' || topic.status === 'running';

/** The signed-in account's topics, oldest first; polled every `pollMs` while one is still being matched. */
export function useResearchTopics(enabled = true, pollMs = 5000) {
  const user = useOptionalAuth()?.user;
  return useQuery({
    queryKey: researchQueryKeys.topics(user?.hf_subject),
    queryFn: researchApi.topics,
    enabled: enabled && !!user,
    refetchInterval: query => query.state.data?.some(isTopicBuilding) ? pollMs : false,
  });
}

/** Adds a topic, or with `id` replaces that topic's text. */
export interface TopicSave {
  id?: number;
  text: string;
}

/** Refreshes the topics and what depends on them; resolves once the topics have reloaded. */
function refreshTopics(client: QueryClient, subject: string | undefined) {
  void invalidateResearch(client, subject, { follows: false });
  return client.invalidateQueries({ queryKey: researchQueryKeys.topics(subject) });
}

/** Saves one of the signed-in account's topics and refreshes what depends on it. */
export function useSaveTopic(onSaved?: () => void) {
  const user = useOptionalAuth()?.user;
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, text }: TopicSave) => id === undefined ? researchApi.addTopic(text) : researchApi.updateTopic(id, text),
    onSuccess: async () => {
      // Any saved topic supersedes one a guest stashed before signing in.
      clearPendingTopic();
      await refreshTopics(client, user?.hf_subject);
      onSaved?.();
    },
  });
}

/** Stops following the given topics, refreshing what depends on them even when some fail. */
export function useRemoveTopics() {
  const user = useOptionalAuth()?.user;
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (ids: number[]) => {
      const results = await Promise.allSettled(ids.map(id => researchApi.removeTopic(id)));
      const failure = results.find((result): result is PromiseRejectedResult => result.status === 'rejected');
      if (failure) throw failure.reason;
    },
    onSettled: () => void refreshTopics(client, user?.hf_subject),
  });
}

// A guest's topic waits here while they sign in, then /following saves it.
const PENDING_TOPIC_KEY = 'pwc:following-pending-topic';

/** Keeps a guest's topic until /following can save it after sign-in. */
export function stashPendingTopic(text: string) {
  sessionStorage.setItem(PENDING_TOPIC_KEY, text);
}

/** The topic a guest submitted before signing in, kept until it is saved. */
export function readPendingTopic(): string | null {
  return sessionStorage.getItem(PENDING_TOPIC_KEY);
}

export function clearPendingTopic() {
  sessionStorage.removeItem(PENDING_TOPIC_KEY);
}

export interface FollowPick {
  kind: FollowKind;
  id: string;
  name: string;
  /** False unfollows; missing or true follows. */
  follow?: boolean;
}

/** Follows or unfollows several entities at once and refreshes what depends on them, even when some fail.
 * Both are idempotent, so a retry may resend the ones that succeeded. */
export function useSaveFollows() {
  const user = useOptionalAuth()?.user;
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (picks: FollowPick[]) => {
      const results = await Promise.allSettled(picks.map(pick => researchApi.setFollow(pick.kind, pick.id, pick.follow ?? true)));
      const failure = results.find((result): result is PromiseRejectedResult => result.status === 'rejected');
      if (failure) throw failure.reason;
    },
    onSuccess: () => clearPendingFollows(),
    onSettled: () => void invalidateResearch(client, user?.hf_subject, { follows: true }),
  });
}

// Tasks and methods a guest picked wait here while they sign in, like the topic.
const PENDING_FOLLOWS_KEY = 'pwc:following-pending-follows';

export function stashPendingFollows(picks: FollowPick[]) {
  sessionStorage.setItem(PENDING_FOLLOWS_KEY, JSON.stringify(picks));
}

export function readPendingFollows(): FollowPick[] {
  return JSON.parse(sessionStorage.getItem(PENDING_FOLLOWS_KEY) ?? '[]');
}

export function clearPendingFollows() {
  sessionStorage.removeItem(PENDING_FOLLOWS_KEY);
}

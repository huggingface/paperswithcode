import { useMutation, useQueryClient } from '@tanstack/react-query';
import { researchApi, type FollowKind } from '@/lib/api/research';
import { useOptionalAuth } from '@/lib/authContext';

/** Saves (or, with `null`, removes) the signed-in account's topic and refreshes what depends on it. */
export function useSaveTopic(onSaved?: () => void) {
  const user = useOptionalAuth()?.user;
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (text: string | null) => text === null ? (await researchApi.clearTopic(), null) : researchApi.setTopic(text),
    onSuccess: data => {
      client.setQueryData(['research-topic', user?.hf_subject], data);
      // Any saved topic supersedes one a guest stashed before signing in.
      clearPendingTopic();
      onSaved?.();
      void client.invalidateQueries({ queryKey: ['research-feed', user?.hf_subject] });
      // Following something turns the weekly email on by default.
      void client.invalidateQueries({ queryKey: ['research-email', user?.hf_subject] });
    },
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
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ['research-follows', user?.hf_subject] });
      void client.invalidateQueries({ queryKey: ['research-feed', user?.hf_subject] });
      void client.invalidateQueries({ queryKey: ['research-email', user?.hf_subject] });
    },
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

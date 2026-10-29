import { useMutation, useQueryClient } from '@tanstack/react-query';
import { researchApi } from '@/lib/api/research';
import { useOptionalAuth } from '@/lib/authContext';

/** Saves (or, with `null`, removes) the signed-in account's topic and refreshes what depends on it. */
export function useSaveTopic(onSaved?: () => void) {
  const user = useOptionalAuth()?.user;
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (text: string | null) => text === null ? (await researchApi.clearTopic(), null) : researchApi.setTopic(text),
    onSuccess: data => {
      client.setQueryData(['research-topic', user?.hf_subject], data);
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

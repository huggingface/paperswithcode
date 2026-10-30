/**
 * Account preferences backed by `/api/v1/me/preferences`.
 *
 * Preferences are stored per HF account on the backend. Signed-in users fetch
 * them once after auth resolves; guests keep the defaults (which means
 * closed-source evaluations are shown) and their changes last until reload.
 * The first preference is `hide_closed_source_evals`, consumed by benchmark
 * and paper evaluation tables.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { accountApi, type UserPreferences } from "./api/account";
import { accountQueryKeys } from "./api/queryKeys";
import { useAuth } from "./authContext";

const DEFAULT_PREFERENCES: UserPreferences = {
  hide_closed_source_evals: false,
};

export function usePreferences() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const queryKey = accountQueryKeys.preferences;
  const query = useQuery({
    queryKey,
    queryFn: () => accountApi.getPreferences(),
    enabled: Boolean(user),
    staleTime: Infinity,
  });
  const preferences = query.data ?? DEFAULT_PREFERENCES;

  const update = useMutation({
    mutationFn: (next: UserPreferences) =>
      user ? accountApi.updatePreferences(next) : Promise.resolve(next),
    // Optimistic update; revert on failure.
    onMutate: async (next) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<UserPreferences>(queryKey) ?? DEFAULT_PREFERENCES;
      queryClient.setQueryData(queryKey, next);
      return { previous };
    },
    onError: (_error, _next, context) => {
      if (context) queryClient.setQueryData(queryKey, context.previous);
    },
    onSuccess: (saved) => queryClient.setQueryData(queryKey, saved),
  });

  return {
    preferences,
    /** True for signed-in users (preferences are persisted server-side). */
    canPersist: Boolean(user),
    isLoading: query.isLoading,
    setHideClosedSourceEvals: (value: boolean) =>
      update.mutate({ ...preferences, hide_closed_source_evals: value }),
  };
}

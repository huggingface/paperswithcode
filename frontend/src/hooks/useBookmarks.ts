import { paperQueryKeys } from "@/lib/paperQueryKeys";
/**
 * Bookmark hooks for the signed-in HF user.
 *
 * `useBookmarkIds` returns a memoised `Set<number>` of paper IDs the user has
 * bookmarked, gated on a valid auth session. `useToggleBookmark` POSTs/DELETEs
 * `/api/v1/me/bookmarks/{id}` and optimistically updates the IDs cache so the
 * Save button flips state without a round-trip.
 *
 * If the user is not signed in, `toggle()` redirects to the HF OAuth login
 * with Saved Papers authorization and resumes the save when the user lands
 * back on the page they came from.
 */

import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { accountApi } from "@/lib/api/account";
import type { BookmarkIdsResponse } from "@/lib/api/account.types";
import { ApiError } from "@/lib/apiTransport";
import { isAuthDisabled } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";
import {
  SAVED_PAPERS_AUTHORIZED_PARAM,
  savedPapersAuthorizationUrl,
} from "@/lib/savedPapersAuth";
import { accountQueryKeys } from "@/lib/api/queryKeys";

const PENDING_BOOKMARK_KEY = "pwc:pending-bookmark";

function authorizeSavedPapers(pending: ToggleArgs) {
  window.sessionStorage.setItem(PENDING_BOOKMARK_KEY, JSON.stringify(pending));
  window.location.assign(savedPapersAuthorizationUrl(true));
}

export function useBookmarkIds() {
  const { user } = useAuth();

  const query = useQuery<BookmarkIdsResponse, Error>({
    queryKey: accountQueryKeys.bookmarkIds,
    queryFn: () => accountApi.getBookmarkIds(),
    enabled: !!user,
    staleTime: 60 * 1000,
  });

  const idSet = React.useMemo(
    () => new Set<number>(query.data?.paper_ids ?? []),
    [query.data?.paper_ids],
  );

  return {
    ids: query.data?.paper_ids ?? [],
    idSet,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

interface ToggleArgs {
  paperId: string | number;
  isBookmarked: boolean;
}

export function useToggleBookmark() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const mutation = useMutation<void, Error, ToggleArgs, { previous?: BookmarkIdsResponse }>(
    {
      mutationFn: async ({ paperId, isBookmarked }) => {
        if (isBookmarked) {
          await accountApi.removeBookmark(paperId);
        } else {
          await accountApi.addBookmark(paperId);
        }
      },
      onMutate: async ({ paperId, isBookmarked }) => {
        await queryClient.cancelQueries({ queryKey: accountQueryKeys.bookmarkIds });
        const previous = queryClient.getQueryData<BookmarkIdsResponse>(accountQueryKeys.bookmarkIds);
        const numericId = typeof paperId === "string" ? Number(paperId) : paperId;
        const currentIds = previous?.paper_ids ?? [];
        const nextIds = isBookmarked
          ? currentIds.filter((id) => id !== numericId)
          : [numericId, ...currentIds.filter((id) => id !== numericId)];
        queryClient.setQueryData<BookmarkIdsResponse>(accountQueryKeys.bookmarkIds, {
          paper_ids: nextIds,
        });
        return { previous };
      },
      onError: (_err, _vars, context) => {
        if (context?.previous) {
          queryClient.setQueryData(accountQueryKeys.bookmarkIds, context.previous);
        }
        if (
          _err instanceof ApiError &&
          _err.code === "saved_papers_bucket_authorization_required"
        ) {
          authorizeSavedPapers(_vars);
        }
      },
      onSettled: () => {
        queryClient.invalidateQueries({ queryKey: accountQueryKeys.bookmarkIds });
        queryClient.invalidateQueries({ queryKey: [...paperQueryKeys.feeds.saved] });
      },
    },
  );

  React.useEffect(() => {
    if (!user || mutation.isPending) return;
    const url = new URL(window.location.href);
    if (url.searchParams.get(SAVED_PAPERS_AUTHORIZED_PARAM) !== "1") return;
    url.searchParams.delete(SAVED_PAPERS_AUTHORIZED_PARAM);
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    const raw = window.sessionStorage.getItem(PENDING_BOOKMARK_KEY);
    if (!raw) return;
    window.sessionStorage.removeItem(PENDING_BOOKMARK_KEY);
    try {
      const pending = JSON.parse(raw) as ToggleArgs;
      if (
        (typeof pending.paperId === "number" || typeof pending.paperId === "string") &&
        typeof pending.isBookmarked === "boolean"
      ) {
        mutation.mutate(pending);
      }
    } catch {
      // Ignore malformed browser state left by an older frontend version.
    }
  }, [mutation, user]);

  const toggle = React.useCallback(
    (paperId: string | number, isBookmarked: boolean) => {
      if (!user) {
        if (isAuthDisabled()) return;
        authorizeSavedPapers({ paperId, isBookmarked });
        return;
      }
      mutation.mutate({ paperId, isBookmarked });
    },
    [mutation, user],
  );

  return { toggle, isPending: mutation.isPending };
}

import { useInfiniteQuery, type QueryKey } from '@tanstack/react-query';

import { FIVE_MINUTES } from "@/lib/api/queries";

/** Infinite paper feed whose pages name the next page to fetch. */
export function usePaperFeedQuery<TPage extends { next_page?: number | null }>(
  queryKey: QueryKey,
  fetchPage: (page: number) => Promise<TPage>,
  { enabled = true, initialPage = 1 }: { enabled?: boolean; initialPage?: number } = {},
) {
  return useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) => fetchPage(pageParam),
    initialPageParam: initialPage,
    getNextPageParam: (lastPage) => lastPage.next_page ?? undefined,
    enabled,
    staleTime: FIVE_MINUTES,
    // Keep showing the old results while a filter changes, but never another feed's.
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[0] === queryKey[0] ? previous : undefined,
  });
}

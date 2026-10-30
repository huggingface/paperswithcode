import { paperQueryKeys } from "@/lib/paperQueryKeys";
import { useQuery, useInfiniteQuery, type QueryKey } from '@tanstack/react-query';
import type { Paper } from '@/lib/api/papers.types';
import { papersApi } from '@/lib/api/papers';
import { TEN_MINUTES } from "@/lib/api/queryKeys";

export function usePaper(id: string, enabled: boolean = true) {
  return useQuery<Paper, Error>({
    queryKey: paperQueryKeys.detail(id),
    queryFn: () => papersApi.get(id),
    enabled: enabled && !!id,
    staleTime: TEN_MINUTES,
  });
}

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
    staleTime: 5 * 60 * 1000,
    // Keep showing the old results while a filter changes, but never another feed's.
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[0] === queryKey[0] ? previous : undefined,
  });
}

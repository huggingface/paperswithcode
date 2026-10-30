import { useEffect } from "react";

import { useIntersectionObserver } from "./useIntersectionObserver";

interface PageableQuery {
  data: unknown;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => Promise<unknown>;
}

/** Fetch the next page while the returned sentinel ref is near the viewport. */
export function useInfiniteScroll(query: PageableQuery, rootMargin = "200px") {
  const { targetRef, isIntersecting } = useIntersectionObserver({ rootMargin });
  const { data, hasNextPage, isFetchingNextPage, fetchNextPage } = query;

  // Also rerun when results change: a filter change can leave the sentinel visible.
  useEffect(() => {
    if (isIntersecting && hasNextPage && !isFetchingNextPage) void fetchNextPage();
  }, [isIntersecting, hasNextPage, isFetchingNextPage, fetchNextPage, data]);

  return targetRef;
}

import { paperQueryKeys } from "@/lib/paperQueryKeys";
import { keepPreviousData, useQuery, useInfiniteQuery } from '@tanstack/react-query';
import type { Paper, PaperOrderBy } from '@/lib/api/papers.types';
import type { PaginatedResponse, PaperSearchFeedPage } from '@/lib/api/shared.types';
import { papersApi } from '@/lib/api/papers';

export function usePaper(id: string, enabled: boolean = true) {
  return useQuery<Paper, Error>({
    queryKey: paperQueryKeys.detail(id),
    queryFn: () => papersApi.get(id),
    enabled: enabled && !!id,
    staleTime: 10 * 60 * 1000, // 10 minutes
    refetchOnWindowFocus: false,
  });
}

interface UseInfinitePapersParams {
  page_size?: number;
  search?: string;
  order_by?: PaperOrderBy;
  order_dir?: 'asc' | 'desc';
  start_date?: string;
  end_date?: string;
  conference?: string;
  task?: string;
  method?: string;
  latest_only?: boolean;
  include_resources?: boolean;
  has_code?: boolean;
  has_hf_artifacts?: boolean;
  framework?: string;
  repository?: string;
  author?: string;
  enabled?: boolean;
}

export function useInfinitePapers(params: UseInfinitePapersParams = {}) {
  const {
    page_size = 20,
    search,
    order_by = 'date_published',
    order_dir = 'desc',
    start_date,
    end_date,
    conference,
    task,
    method,
    latest_only = true,
    include_resources = false,
    has_code = false,
    has_hf_artifacts = false,
    framework,
    repository,
    author,
    enabled = true,
  } = params;

  return useInfiniteQuery<PaginatedResponse<Paper>, Error>({
    queryKey: [...paperQueryKeys.feeds.infinite, { page_size, search, order_by, order_dir, start_date, end_date, conference, task, method, latest_only, include_resources, has_code, has_hf_artifacts, framework, repository, author }],
    queryFn: ({ pageParam = 1 }) =>
      papersApi.list({
        page: pageParam as number,
        page_size,
        search,
        order_by,
        order_dir,
        start_date,
        end_date,
        conference,
        task,
        method,
        latest_only,
        include_resources,
        has_code,
        has_hf_artifacts,
        framework,
        repository,
        author,
      }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}

interface UseInfinitePaperSearchParams {
  q: string;
  order_by?: 'relevance' | 'date_published' | 'citation_count';
  start_date?: string;
  end_date?: string;
  has_code?: boolean;
  has_hf_artifacts?: boolean;
  enabled?: boolean;
}

export function useInfinitePaperSearch({
  q,
  order_by = 'relevance',
  start_date,
  end_date,
  has_code = false,
  has_hf_artifacts = false,
  enabled = true,
}: UseInfinitePaperSearchParams) {
  return useInfiniteQuery<PaperSearchFeedPage<Paper>, Error>({
    queryKey: [...paperQueryKeys.feeds.search, { q, order_by, start_date, end_date, has_code, has_hf_artifacts }],
    queryFn: ({ pageParam = 1 }) => papersApi.searchFeed({
      q,
      page: pageParam as number,
      page_size: 20,
      order_by,
      start_date,
      end_date,
      has_code,
      has_hf_artifacts,
      mode: 'hybrid',
    }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled: enabled && q.trim().length > 0,
    staleTime: 5 * 60 * 1000,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}

interface UseInfiniteTaskPapersParams {
  taskId: string;
  page_size?: number;
  order_by?: 'trending' | 'date_published' | 'citation_count' | 'title';
  order_dir?: 'asc' | 'desc';
  latest_only?: boolean;
  include_resources?: boolean;
  has_code?: boolean;
  has_hf_artifacts?: boolean;
  start_date?: string;
  end_date?: string;
  enabled?: boolean;
}

export function useInfiniteTaskPapers(params: UseInfiniteTaskPapersParams) {
  const {
    taskId,
    page_size = 20,
    order_by = 'date_published',
    order_dir = 'desc',
    latest_only = true,
    include_resources = true,
    has_code = false,
    has_hf_artifacts = false,
    start_date,
    end_date,
    enabled = true,
  } = params;

  return useInfiniteQuery<PaginatedResponse<Paper>, Error>({
    queryKey: [...paperQueryKeys.feeds.task, taskId, { page_size, order_by, order_dir, latest_only, include_resources, has_code, has_hf_artifacts, start_date, end_date }],
    queryFn: ({ pageParam = 1 }) =>
      papersApi.forTask(taskId, {
        page: pageParam as number,
        page_size,
        order_by,
        order_dir,
        latest_only,
        include_resources,
        // Cards show only the leading repository; highly cited papers can
        // otherwise carry hundreds of community implementations each.
        repository_limit: 1,
        has_code,
        has_hf_artifacts,
        start_date,
        end_date,
      }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled: enabled && !!taskId,
    staleTime: 5 * 60 * 1000, // 5 minutes
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}

interface UseInfiniteConferencePapersParams {
  conferenceSlug: string;
  taskSlug?: string;
  presentation?: 'oral' | 'spotlight' | 'outstanding' | 'best_paper_finalist';
  page_size?: number;
  order_by?: 'trending' | 'date_published' | 'citation_count' | 'title';
  order_dir?: 'asc' | 'desc';
  latest_only?: boolean;
  include_resources?: boolean;
  has_code?: boolean;
  has_hf_artifacts?: boolean;
  start_date?: string;
  end_date?: string;
  enabled?: boolean;
}

export function useInfiniteConferencePapers(params: UseInfiniteConferencePapersParams) {
  const {
    conferenceSlug,
    taskSlug,
    presentation,
    page_size = 20,
    order_by = 'date_published',
    order_dir = 'desc',
    latest_only = true,
    include_resources = true,
    has_code = false,
    has_hf_artifacts = false,
    start_date,
    end_date,
    enabled = true,
  } = params;

  return useInfiniteQuery<PaginatedResponse<Paper>, Error>({
    queryKey: [...paperQueryKeys.feeds.conference, conferenceSlug, taskSlug, presentation, { page_size, order_by, order_dir, latest_only, include_resources, has_code, has_hf_artifacts, start_date, end_date }],
    queryFn: ({ pageParam = 1 }) =>
      papersApi.forConference(conferenceSlug, {
        task: taskSlug,
        presentation,
        page: pageParam as number,
        page_size,
        order_by,
        order_dir,
        latest_only,
        include_resources,
        has_code,
        has_hf_artifacts,
        start_date,
        end_date,
      }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled: enabled && !!conferenceSlug,
    staleTime: 5 * 60 * 1000,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}

interface UseInfiniteOrganizationPapersParams {
  organizationSlug: string;
  taskSlug?: string;
  page_size?: number;
  order_by?: 'trending' | 'date_published' | 'citation_count' | 'title';
  order_dir?: 'asc' | 'desc';
  latest_only?: boolean;
  include_resources?: boolean;
  has_code?: boolean;
  has_hf_artifacts?: boolean;
  start_date?: string;
  end_date?: string;
  enabled?: boolean;
}

export function useInfiniteOrganizationPapers(params: UseInfiniteOrganizationPapersParams) {
  const {
    organizationSlug,
    taskSlug,
    page_size = 20,
    order_by = 'date_published',
    order_dir = 'desc',
    latest_only = true,
    include_resources = true,
    has_code = false,
    has_hf_artifacts = false,
    start_date,
    end_date,
    enabled = true,
  } = params;

  return useInfiniteQuery<PaginatedResponse<Paper>, Error>({
    queryKey: [...paperQueryKeys.feeds.organization, organizationSlug, taskSlug, { page_size, order_by, order_dir, latest_only, include_resources, has_code, has_hf_artifacts, start_date, end_date }],
    queryFn: ({ pageParam = 1 }) =>
      papersApi.forOrganization(organizationSlug, {
        task: taskSlug,
        page: pageParam as number,
        page_size,
        order_by,
        order_dir,
        latest_only,
        include_resources,
        has_code,
        has_hf_artifacts,
        start_date,
        end_date,
      }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled: enabled && !!organizationSlug,
    staleTime: 5 * 60 * 1000,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}

import { queryOptions, skipToken } from "@tanstack/react-query";

import { accountApi } from "@/lib/api/account";
import { authApi } from "@/lib/api/auth";
import { catalogApi } from "@/lib/api/catalog";
import { codexApi, type CodexPaperJobKind } from "@/lib/api/codex";
import type { CodexJobFilters } from "@/lib/api/codex.types";
import { evaluationsApi } from "@/lib/api/evaluations";
import { operationsApi } from "@/lib/api/operations";
import { paperEditsApi } from "@/lib/api/paperEdits";
import { getPaperLayout, getPaperWebMarkdown, getPaperWebPage, papersApi } from "@/lib/api/papers";
import { profilesApi } from "@/lib/api/profiles";
import { researchApi } from "@/lib/api/research";
import { statsApi } from "@/lib/api/stats";

/**
 * The one place that names React Query cache entries.
 *
 * Every key is `[family, identifier?, ...params]`: `key[0]` names the cache
 * family (what invalidation and feed placeholders match on), `key[1]` is the
 * entity the entry is about, and request parameters follow. Readers get
 * `queryOptions` from the factories below, so a key is always built from the
 * request it caches and two readers of one request share one entry.
 */

export const ONE_MINUTE = 60 * 1000;
export const FIVE_MINUTES = 5 * ONE_MINUTE;
/** The usual `staleTime` for catalog reads. */
export const TEN_MINUTES = 10 * ONE_MINUTE;
export const ONE_HOUR = 60 * ONE_MINUTE;

type Params<F extends (...args: never[]) => unknown, I extends number = 0> = NonNullable<Parameters<F>[I]>;

/** Run the request only once its identifier is known. */
const when = <T, R>(value: T | null | undefined, fetch: (value: T) => Promise<R>) =>
  value == null || value === "" ? skipToken : () => fetch(value);

export const authQueries = {
  me: () => queryOptions({
    queryKey: ["auth", "me"],
    queryFn: () => authApi.getCurrentUser(),
    staleTime: Infinity,
  }),
};

export const accountQueries = {
  preferences: () => queryOptions({
    queryKey: ["account", "preferences"],
    queryFn: () => accountApi.getPreferences(),
    staleTime: Infinity,
  }),
  bookmarkIds: () => queryOptions({
    queryKey: ["my-bookmark-ids"],
    queryFn: () => accountApi.getBookmarkIds(),
  }),
  rateLimitPolicy: () => queryOptions({
    queryKey: ["submission-rate-limit-policy"],
    queryFn: () => accountApi.getRateLimitPolicy(),
  }),
};

export const catalogKeys = {
  /** Prefix of every organization list. */
  organizations: ["organizations"] as const,
};

export const catalogQueries = {
  areas: () => queryOptions({
    queryKey: ["areas"],
    queryFn: () => catalogApi.listAreas({ page_size: 50, ordering: "name" }),
    staleTime: TEN_MINUTES,
  }),
  area: (id: string | undefined) => queryOptions({
    queryKey: ["area", id],
    queryFn: when(id, (areaId) => catalogApi.getArea(areaId)),
    staleTime: TEN_MINUTES,
  }),
  areasWithTasks: () => queryOptions({
    queryKey: ["areas-with-tasks"],
    queryFn: () => catalogApi.areasWithTasks(),
    staleTime: TEN_MINUTES,
  }),
  topTasks: (limit: number) => queryOptions({
    queryKey: ["top-tasks", limit],
    queryFn: () => catalogApi.topTasks(limit),
    staleTime: TEN_MINUTES,
  }),
  trendingTasks: (params: Params<typeof catalogApi.trendingTasks>) => queryOptions({
    queryKey: ["trending-tasks", params],
    queryFn: () => catalogApi.trendingTasks(params),
    staleTime: TEN_MINUTES,
  }),
  trendingMethods: (params: Params<typeof catalogApi.trendingMethods>) => queryOptions({
    queryKey: ["trending-methods", params],
    queryFn: () => catalogApi.trendingMethods(params),
    staleTime: TEN_MINUTES,
  }),
  taskList: (params: Params<typeof catalogApi.listTasks>) => queryOptions({
    queryKey: ["task-list", params],
    queryFn: () => catalogApi.listTasks(params),
  }),
  methodList: (params: Params<typeof catalogApi.listMethods>) => queryOptions({
    queryKey: ["method-list", params],
    queryFn: () => catalogApi.listMethods(params),
  }),
  datasetList: (params: Params<typeof catalogApi.listDatasets>) => queryOptions({
    queryKey: ["dataset-list", params],
    queryFn: () => catalogApi.listDatasets(params),
  }),
  /** Entity readers key by ID or slug; the responses are canonical. */
  task: (idOrSlug: string | undefined) => queryOptions({
    queryKey: ["task", idOrSlug],
    queryFn: when(idOrSlug, (id) => catalogApi.getTask(id)),
    staleTime: TEN_MINUTES,
  }),
  taskPage: (slug: string | undefined, params: Params<typeof catalogApi.taskPage, 1>) => queryOptions({
    queryKey: ["task-page", slug, params],
    queryFn: when(slug, (taskSlug) => catalogApi.taskPage(taskSlug, params)),
    staleTime: TEN_MINUTES,
  }),
  taskBenchmarkTrends: (
    idOrSlug: string | undefined,
    params: Params<typeof catalogApi.trendingBenchmarks, 1>,
  ) => queryOptions({
    queryKey: ["task-benchmark-trends", idOrSlug, params],
    queryFn: when(idOrSlug, (id) => catalogApi.trendingBenchmarks(id, params)),
    staleTime: TEN_MINUTES,
  }),
  method: (idOrSlug: string | undefined) => queryOptions({
    queryKey: ["method", idOrSlug],
    queryFn: when(idOrSlug, (id) => catalogApi.getMethod(id)),
    staleTime: TEN_MINUTES,
  }),
  methodIndex: () => queryOptions({
    queryKey: ["method-index"],
    queryFn: () => catalogApi.methodIndex(),
    staleTime: TEN_MINUTES,
  }),
  methodTrend: (slug: string | undefined) => queryOptions({
    queryKey: ["method-trend", slug],
    queryFn: when(slug, (id) => catalogApi.methodTrend(id)),
    staleTime: TEN_MINUTES,
  }),
  relatedMethods: (slug: string | undefined) => queryOptions({
    queryKey: ["related-methods", slug],
    queryFn: when(slug, (id) => catalogApi.relatedMethods(id)),
    staleTime: TEN_MINUTES,
  }),
  dataset: (idOrSlug: string | undefined) => queryOptions({
    queryKey: ["dataset", idOrSlug],
    queryFn: when(idOrSlug, (id) => catalogApi.getDataset(id)),
    staleTime: TEN_MINUTES,
  }),
  /** A benchmark page's dataset, with its paper and the leaderboard's task. */
  datasetPage: (slug: string | undefined, params: Params<typeof catalogApi.getDatasetBySlug, 1>) => queryOptions({
    queryKey: ["dataset", slug, params],
    queryFn: when(slug, (datasetSlug) => catalogApi.getDatasetBySlug(datasetSlug, params)),
    staleTime: TEN_MINUTES,
  }),
  datasetTasks: (datasetId: string | undefined) => queryOptions({
    queryKey: ["dataset-tasks", datasetId],
    queryFn: when(datasetId, (id) => catalogApi.datasetTasks(id)),
    staleTime: TEN_MINUTES,
  }),
  leaderboardMetrics: (datasetId: string | undefined, taskId: string | undefined) => queryOptions({
    queryKey: ["leaderboard-metrics", datasetId, taskId],
    queryFn: datasetId && taskId ? () => catalogApi.leaderboardMetrics(datasetId, taskId) : skipToken,
    staleTime: TEN_MINUTES,
  }),
  metricDirections: () => queryOptions({
    queryKey: ["metric-directions"],
    queryFn: () => catalogApi.metricDirections(),
    staleTime: ONE_HOUR,
  }),
  frameworkCatalog: () => queryOptions({
    queryKey: ["framework-catalog"],
    queryFn: () => catalogApi.frameworkCatalog(),
  }),
  conferences: () => queryOptions({
    queryKey: ["conferences"],
    queryFn: () => catalogApi.conferences(),
    staleTime: TEN_MINUTES,
  }),
  conferenceDeadlines: () => queryOptions({
    queryKey: ["conference-deadlines"],
    queryFn: () => catalogApi.conferenceDeadlines(),
    staleTime: TEN_MINUTES,
  }),
  conference: (slug: string | undefined) => queryOptions({
    queryKey: ["conference", slug],
    queryFn: when(slug, (id) => catalogApi.getConference(id)),
    staleTime: TEN_MINUTES,
  }),
  conferenceAreasWithTasks: (slug: string | undefined) => queryOptions({
    queryKey: ["conference-areas-with-tasks", slug],
    queryFn: when(slug, (id) => catalogApi.conferenceAreasWithTasks(id)),
    staleTime: TEN_MINUTES,
  }),
  /** Every organization family starts with "organizations" so one edit refreshes them all. */
  organizations: () => queryOptions({
    queryKey: ["organizations", "all"],
    queryFn: () => catalogApi.organizations(),
    staleTime: FIVE_MINUTES,
  }),
  organizationIndex: () => queryOptions({
    queryKey: ["organizations", "index"],
    queryFn: () => catalogApi.organizationIndex(),
    staleTime: TEN_MINUTES,
  }),
  organizationSearch: (q: string, limit: number) => queryOptions({
    queryKey: ["organizations", "search", q, limit],
    queryFn: () => catalogApi.searchOrganizations(q, limit),
  }),
  organization: (slug: string | undefined) => queryOptions({
    queryKey: ["organization", slug],
    queryFn: when(slug, (id) => catalogApi.getOrganization(id)),
    staleTime: TEN_MINUTES,
  }),
  organizationAreasWithTasks: (slug: string) => queryOptions({
    queryKey: ["organization-areas-with-tasks", slug],
    queryFn: () => catalogApi.organizationAreasWithTasks(slug),
    staleTime: TEN_MINUTES,
  }),
  organizationContributions: (slug: string) => queryOptions({
    queryKey: ["organization-contributions", slug],
    queryFn: () => catalogApi.organizationContributions(slug),
    staleTime: TEN_MINUTES,
  }),
};

export const paperQueries = {
  /** The paper page: the paper with all of its resources. */
  detail: (id: string | undefined) => queryOptions({
    queryKey: ["paper", id],
    queryFn: when(id, (paperId) => papersApi.get(paperId, true)),
    staleTime: TEN_MINUTES,
  }),
  /** The paper without resources, for hover cards and review lists. Keyed by any route ID. */
  summary: (routeId: string) => queryOptions({
    queryKey: ["paper-summary", routeId],
    queryFn: () => papersApi.get(routeId, false),
    staleTime: FIVE_MINUTES,
  }),
  versions: (arxivId: string | undefined) => queryOptions({
    queryKey: ["paper-versions", arxivId],
    queryFn: when(arxivId, (id) => papersApi.versions(id)),
    staleTime: TEN_MINUTES,
  }),
  related: (routeId: string | undefined) => queryOptions({
    queryKey: ["related-papers", routeId],
    queryFn: when(routeId, (id) => papersApi.related(id, 4)),
    staleTime: TEN_MINUTES,
  }),
  search: (q: string, pageSize: number) => queryOptions({
    queryKey: ["paper-search", q, pageSize],
    queryFn: () => papersApi.search(q, 1, pageSize),
    staleTime: ONE_MINUTE,
  }),
  saved: () => queryOptions({
    queryKey: ["my-bookmarks"],
    queryFn: () => accountApi.getBookmarks(),
  }),
  layout: (routeId: string) => queryOptions({
    queryKey: ["paper-layout", routeId],
    queryFn: () => getPaperLayout(routeId),
    staleTime: FIVE_MINUTES,
  }),
  webPage: (paperId: string) => queryOptions({
    queryKey: ["paper-web-page", paperId],
    queryFn: () => getPaperWebPage(paperId),
    staleTime: FIVE_MINUTES,
  }),
  webMarkdown: (paperId: string) => queryOptions({
    queryKey: ["paper-web-markdown", paperId],
    queryFn: () => getPaperWebMarkdown(paperId),
    staleTime: FIVE_MINUTES,
  }),
  suggestedQuestions: (paperId: string) => queryOptions({
    queryKey: ["paper-suggested-questions", paperId],
    queryFn: () => papersApi.suggestedQuestions(paperId),
  }),
  author: (id: string) => queryOptions({
    queryKey: ["author", id],
    queryFn: () => papersApi.getAuthor(id),
    staleTime: FIVE_MINUTES,
  }),
  authorSearch: (q: string, pageSize: number) => queryOptions({
    queryKey: ["author-search", q, pageSize],
    queryFn: () => papersApi.searchAuthors(q, pageSize),
    staleTime: ONE_MINUTE,
  }),
};

/**
 * Infinite paper lists. Feeds fetch their own pages (page sizes and paging
 * differ per view), so these name only the key; `PAPER_LIST_FAMILIES` is what
 * a paper edit stales.
 */
const FEED = {
  list: "papers-infinite",
  search: "paper-search-feed",
  task: "task-papers-infinite",
  conference: "conference-papers-infinite",
  organization: "organization-papers-infinite",
  method: "method-papers-infinite",
  following: "research-feed",
  trending: "trending-papers",
} as const;

export const paperFeedKeys = {
  list: (filters: object) => [FEED.list, filters] as const,
  search: (filters: object) => [FEED.search, filters] as const,
  task: (slug: string | undefined, filters: object) => [FEED.task, slug, filters] as const,
  conference: (conference: string | undefined, task: string | undefined, filters: object) =>
    [FEED.conference, conference, task, filters] as const,
  organization: (slug: string, task: string | undefined, filters: object) =>
    [FEED.organization, slug, task, filters] as const,
  method: (slug: string | undefined, filters: object) => [FEED.method, slug, filters] as const,
  /** Without filters, every following feed of that subject. */
  following: (subject: string | undefined, filters?: object) =>
    filters ? [FEED.following, subject, filters] as const : [FEED.following, subject] as const,
  trending: (filters: object) => [FEED.trending, filters] as const,
};

/** Every cache family listing papers; membership and ordering may change with any paper edit. */
export const PAPER_LIST_FAMILIES: readonly string[] = [
  ...Object.values(FEED),
  "my-bookmarks",
  "related-papers",
  "paper-versions",
  "paper-search",
  // Chat's mention picker (components/chat/usePaperMentions.ts).
  "chat-paper-mention-search",
];

export const evaluationQueries = {
  byPaper: (paperId: string | undefined) => queryOptions({
    queryKey: ["paper-evals", paperId],
    queryFn: when(paperId, (id) => evaluationsApi.byPaper(id)),
    staleTime: 0,
  }),
  byDataset: (datasetId: string | undefined) => queryOptions({
    queryKey: ["dataset-evals", datasetId],
    queryFn: when(datasetId, (id) => evaluationsApi.byDataset(id)),
    staleTime: FIVE_MINUTES,
  }),
};

export const researchQueries = {
  follows: (subject: string | undefined) => queryOptions({
    queryKey: ["research-follows", subject],
    queryFn: researchApi.follows,
  }),
  followSuggestions: () => queryOptions({
    queryKey: ["research-follow-suggestions"],
    queryFn: researchApi.followSuggestions,
    staleTime: TEN_MINUTES,
  }),
  topics: (subject: string | undefined) => queryOptions({
    queryKey: ["research-topics", subject],
    queryFn: researchApi.topics,
  }),
  publicTopic: (id: number, subject: string | undefined) => queryOptions({
    queryKey: ["research-public-topic", id, subject],
    queryFn: () => researchApi.publicTopic(id),
  }),
  followingNewCount: (subject: string | undefined, since: string) => queryOptions({
    queryKey: ["research-following-new-count", subject, since],
    queryFn: () => researchApi.followingNewCount(since),
    staleTime: 5 * 60 * 1000,
  }),
  featuredTopics: () => queryOptions({
    queryKey: ["research-featured-topics"],
    queryFn: researchApi.featuredTopics,
    staleTime: TEN_MINUTES,
  }),
  topicMatches: (text: string) => queryOptions({
    queryKey: ["research-topic-matches", text],
    queryFn: () => researchApi.topicMatches(text),
    staleTime: TEN_MINUTES,
  }),
  email: (subject: string | undefined) => queryOptions({
    queryKey: ["research-email", subject],
    queryFn: researchApi.email,
  }),
};

export const statsQueries = {
  trends: () => queryOptions({
    queryKey: ["research-trends"],
    queryFn: () => statsApi.trends(),
    staleTime: ONE_HOUR,
  }),
};

export const researchKeys = {
  /** Prefix of every public topic entry. */
  publicTopics: ["research-public-topic"] as const,
  // The topic id leads the key: paper feeds keep placeholder data only within one key[0],
  // so another topic never shows this one's papers while loading.
  topicPapers: (id: number, order: string, range: { startDate?: string; endDate?: string }, subject: string | undefined) =>
    [`research-topic-papers-${id}`, order, range.startDate ?? null, range.endDate ?? null, subject] as const,
};

export const profileQueries = {
  user: (username: string) => queryOptions({
    queryKey: ["user-profile", username.toLowerCase()],
    queryFn: () => profilesApi.get(username),
  }),
};

export const paperEditQueries = {
  authorization: (authorizationId: string) => queryOptions({
    queryKey: ["paper-edit-authorization", authorizationId],
    queryFn: () => paperEditsApi.authorization(authorizationId),
  }),
  digest: (day: string, page: number) => queryOptions({
    queryKey: ["paper-edit-digest", day, page],
    queryFn: when(day, (date) => paperEditsApi.digest(date, page)),
  }),
};

export const submissionKeys = {
  pendingEdits: ["pendingPaperEdits"] as const,
  counts: (editType: string, autoOnly: boolean) => ["pendingPaperEdits", "counts", editType, autoOnly] as const,
  list: (filters: { status: string; editType: string; autoOnly: boolean }) => ["pendingPaperEdits", filters] as const,
};

export const adminKeys = {
  all: ["admin"] as const,
  cronStatus: ["admin", "cronStatus"] as const,
  chatSandboxSpend: (environment: string) => ["admin", "chatSandboxSpend", environment] as const,
  chatWebSearchBudget: ["admin", "chatWebSearchBudget"] as const,
  codexPaperJobs: ["admin", "codexPaperJobs"] as const,
  catalogAudit: ["catalog-audit"] as const,
};

export const adminQueries = {
  cronStatus: () => queryOptions({
    queryKey: adminKeys.cronStatus,
    queryFn: () => operationsApi.getCronStatus(),
  }),
  autonomousOperations: () => queryOptions({
    queryKey: ["admin", "autonomousOperations"],
    queryFn: () => operationsApi.getAutonomousOperations(),
  }),
  paperMarkdownJobs: () => queryOptions({
    queryKey: ["admin", "paperMarkdownJobs"],
    queryFn: () => operationsApi.getPaperMarkdownJobs(),
  }),
  codexPaperJobs: (filters: CodexJobFilters) => queryOptions({
    queryKey: [...adminKeys.codexPaperJobs, filters],
    queryFn: () => codexApi.listJobs(100, filters),
  }),
  codexPaperJob: (kind: CodexPaperJobKind, jobId: string | null) => queryOptions({
    queryKey: ["admin", "codexPaperJob", kind, jobId],
    queryFn: when(jobId, (id) => codexApi.getPaperJob(kind, id)),
  }),
};

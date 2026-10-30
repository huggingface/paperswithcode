import { paperQueryKeys } from "@/lib/paperQueryKeys";

/** The usual `staleTime` for catalog reads. */
export const TEN_MINUTES = 10 * 60 * 1000;

/** Cache families per domain. Arrays are prefixes: spread them to add filters. */
export const authQueryKeys = {
  me: ["auth", "me"],
} as const;

export const accountQueryKeys = {
  preferences: ["account", "preferences"],
  bookmarkIds: ["my-bookmark-ids"],
} as const;

export const catalogQueryKeys = {
  areas: ["areas-all"],
  area: (id: string | number | undefined) => ["area", id] as const,
  topTasksSidebar: ["top-tasks-sidebar"],
  /** Entity readers key by ID or slug; the responses are canonical. */
  task: (idOrSlug: string | undefined) => ["task", idOrSlug] as const,
  method: (idOrSlug: string | undefined) => ["method", idOrSlug] as const,
  organization: (idOrSlug: string | undefined) => ["organization", idOrSlug] as const,
  dataset: (idOrSlug: string | undefined) => ["dataset", idOrSlug] as const,
  datasets: ["dataset"],
  datasetTasks: ["dataset-tasks"],
  taskPage: ["task-page"],
  taskBenchmarkTrends: ["task-benchmark-trends"],
  organizations: ["organizations"],
} as const;

export const evaluationQueryKeys = {
  all: ["evaluations"],
  byPaper: (paperId: string | undefined) => ["evaluations", "paper", paperId] as const,
  byPaperAll: ["evaluations", "paper"],
  byDatasetAll: ["dataset-evals"],
  byDataset: (datasetId: string | undefined) => ["dataset-evals", datasetId] as const,
} as const;

export const submissionQueryKeys = {
  pendingEdits: ["pendingPaperEdits"],
} as const;

export const adminQueryKeys = {
  all: ["admin"],
  cronStatus: ["admin", "cronStatus"],
  chatSandboxSpend: (environment: string) => ["admin", "chatSandboxSpend", environment] as const,
  chatWebSearchBudget: ["admin", "chatWebSearchBudget"],
  autonomousOperations: ["admin", "autonomousOperations"],
  paperMarkdownJobs: ["admin", "paperMarkdownJobs"],
  codexPaperJobs: ["admin", "codexPaperJobs"],
  codexPaperJob: (kind: string, id: string | null) => ["admin", "codexPaperJob", kind, id] as const,
  catalogAudit: ["catalog-audit"],
} as const;

export const researchQueryKeys = {
  follows: (subject: string | undefined) => ["research-follows", subject] as const,
  topic: (subject: string | undefined) => ["research-topic", subject] as const,
  email: (subject: string | undefined) => ["research-email", subject] as const,
  feed: (subject: string | undefined) => [...paperQueryKeys.feeds.following, subject] as const,
} as const;

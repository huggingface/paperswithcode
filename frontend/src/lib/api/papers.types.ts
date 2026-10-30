import type { Method, OrganizationSummary, Task } from "./catalog.types";

export interface Repository {
  id: string;
  paper_id: string;
  url: string;
  owner?: string;
  name?: string;
  num_stars: number;
  trending_score?: number | null;
  trending_score_updated_at?: string | null;
  is_official: boolean;
  source: string;
  created_at?: string;
  updated_at?: string;
}

interface ProjectPage {
  id: string;
  paper_id: string;
  url: string;
  is_official: boolean;
  source: string;
  created_at?: string;
  updated_at?: string;
}

/** An X post introducing a paper, previewed when it was linked. */
export interface XThread {
  url: string;
  tweet_id: string;
  author_name: string;
  author_handle: string;
  author_avatar_url?: string | null;
  text: string;
  posted_at?: string | null;
  like_count?: number | null;
  reply_count?: number | null;
  media_url?: string | null;
  media_type?: "photo" | "video" | null;
  video_url?: string | null;
  fetched_at: string;
}

/** Compact Hugging Face artifact summary for paper cards: per-kind counts plus
 *  the most populated category and a link to it. */
interface HfArtifactSummary {
  model_count: number;
  dataset_count: number;
  space_count: number;
  /** 'model' | 'dataset' | 'space'; null when no artifacts exist. */
  best_kind: 'model' | 'dataset' | 'space' | null;
  best_count: number;
  best_url: string | null;
}

/** Hub links stored by the HF sync, most popular first (paper detail only). */
interface LinkedHfArtifacts {
  models: string[];
  datasets: string[];
  spaces: string[];
}

interface BenchmarkSummary {
  id: string;
  name: string;
  slug?: string;
  full_name?: string;
  introduced_year?: number;
}

interface FrameworkSummary {
  id: string;
  slug: string;
  name: string;
}

/** A top-3 leaderboard placement for a paper, used to render the SOTA/#2/#3
 *  badges on feed cards. One entry per benchmark (dataset), deduped to the
 *  paper's best rank on that benchmark. */
export interface LeaderboardRankSummary {
  evaluation_id: string;
  dataset_name: string;
  dataset_slug?: string | null;
  best_rank: number;
  best_metric?: string | null;
  task_slug?: string | null;
}

/** Lightweight summary of a related paper (predecessor or successor)
 *  embedded in the paper detail response. Used to power the lineage banner
 *  on the paper page (e.g. DINOv2 -> DINOv3). */
interface RelatedPaperSummary {
  id: string;
  title: string;
  arxiv_id: string | null;
  source?: 'arxiv' | 'external';
  source_url?: string | null;
  published?: string | null;
  /** Identifier the frontend should use when building the paper detail URL:
   *  ArXiv ID for ArXiv rows, internal numeric ID otherwise. */
  route_identifier: string;
}

export interface RelatedPaperRecommendation {
  id: string;
  title: string;
  arxiv_id: string | null;
  source?: 'arxiv' | 'external';
  source_url?: string | null;
  published?: string | null;
  citation_count: number;
  provenance: 'dense' | 'hybrid' | 'lexical' | 'task_fallback';
  similarity?: number | null;
  generation_id?: number | null;
  used_stale_source_vector: boolean;
}

/** One linked catalog name in a paper abstract. */
export interface AbstractMention {
  start: number;
  end: number;
  surface: string;
  entity_type: "method" | "benchmark" | "framework";
  slug: string;
  name: string;
  /** Hover-card content sent with the paper, so cards open without a fetch. */
  preview?: {
    name: string;
    description?: string | null;
    image_url?: string | null;
    count?: number | null;
    detail?: string | null;
  } | null;
}

export interface Paper {
  id: string;
  arxiv_id: string | null;
  source?: 'arxiv' | 'external';
  source_url?: string | null;
  url_abs: string | null;
  url_pdf: string | null;
  thumbnail_url?: string;
  title: string;
  abstract: string;
  tldr?: string | null;
  /** Detail responses only: stored questions, [] when none are stored yet. */
  suggested_questions?: string[] | null;
  evaluated_benchmarks?: string[] | null;
  page_title?: string | null;
  num_pages?: number | null;
  authors: string[];
  /** Parallel to `authors`. When present, includes hf_username so the frontend
   *  can link names to the matching huggingface.co profile. */
  author_links?: AuthorLink[];
  published: string;
  conference?: string;
  conference_url_abs?: string;
  conference_url_pdf?: string;
  proceeding?: string;
  conference_slug?: string;
  conference_name?: string;
  conference_award?: 'outstanding' | 'honorable_mention' | 'best_paper_finalist' | null;
  version: string;
  is_latest_version: boolean;
  citation_count: number;
  semantic_scholar_id?: string;
  repositories?: Repository[];
  project_pages?: ProjectPage[];
  /** X (formerly Twitter) posts in which the authors introduce the paper. */
  x_threads?: XThread[];
  /** Catalog names linked in the abstract, as character spans of `abstract`
   *  (paper detail only). */
  abstract_mentions?: AbstractMention[];
  /** Hugging Face model URLs explicitly linked to this paper. Populated for
   *  external rows only; arXiv rows derive HF artifacts from `arxiv_id`. */
  hf_models?: string[];
  /** Hugging Face dataset URLs explicitly linked to this paper. External rows only. */
  hf_datasets?: string[];
  /** Hugging Face Space URLs explicitly linked to this paper. External rows only. */
  hf_spaces?: string[];
  /** Compact HF artifact summary used by feed cards (counts + best-category link). */
  hf_artifact_summary?: HfArtifactSummary | null;
  /** Up to 100 stored Hub links per kind; returned with include_resources. */
  linked_hf_artifacts?: LinkedHfArtifacts | null;
  tasks?: Task[];
  methods?: Method[];
  introduced_benchmarks?: BenchmarkSummary[];
  introduced_frameworks?: FrameworkSummary[];
  /** Earlier papers that this paper is a follow-up to (e.g. DINOv2 for the
   *  DINOv3 paper). Powers the "Predecessor paper" pill in the lineage
   *  banner on the paper detail view. */
  predecessor_papers?: RelatedPaperSummary[];
  /** Later papers that follow up on this paper (e.g. DINOv3 for the DINOv2
   *  paper). Powers the "Follow-up paper" pill in the lineage banner on the
   *  paper detail view. */
  successor_papers?: RelatedPaperSummary[];
  /** Organizations (labs/companies) this paper is attributed to, e.g. NVIDIA.
   *  Includes association provenance and the manual curator when known. */
  organizations?: OrganizationSummary[];
  /** Top-3 leaderboard placements (best_rank <= 3) for this paper, deduped by
   *  dataset. Powers the SOTA/#2/#3 badges on feed cards. */
  leaderboard_ranks?: LeaderboardRankSummary[];
}

export interface PaperBucketCopyRequest {
  bucket_id: string;
  create: boolean;
  private: boolean;
  include_pdf: boolean;
  artifacts: Array<{ kind: 'model' | 'dataset' | 'space'; repo_id: string }>;
}

export interface PaperBucketCopyResponse {
  bucket_id: string;
  copied: string[];
  errors: Array<{ artifact: string; message: string }>;
}

export interface Author {
  id: string;
  full_name: string;
  hf_username?: string | null;
  hf_avatar_url?: string | null;
  /** Set only when the Scholar profile was verified against the author's papers. */
  google_scholar_id?: string | null;
  /** Freely licensed portrait, shown with its credit, for authors without an HF avatar. */
  photo?: AuthorPhoto | null;
  organization_slug?: string | null;
  paper_count: number;
}

export interface AuthorPhoto {
  url: string;
  credit: string;
  license: string;
  license_url: string | null;
  source_url: string;
}

interface AuthorLink {
  id?: string | null;
  name: string;
  hf_username?: string | null;
  hf_avatar_url?: string | null;
}

export type PaperOrderBy = 'trending' | 'date_published' | 'citation_count';
export type PaperSearchMode = 'keyword' | 'semantic' | 'hybrid';

interface TrendingMetrics {
  velocity_24h: number;
  trending_score: number;
  stars_gained_24h: number;
}

export interface TrendingPaper {
  paper_id: string;
  arxiv_id: string | null;
  title: string;
  abstract: string | null;
  authors: string[];
  date_published: string | null;
  thumbnail_url?: string;
  tasks?: Array<{ name: string; slug: string }>;
  repository: {
    id: string;
    url: string;
    owner: string;
    name: string;
    num_stars: number;
  };
  trending: TrendingMetrics;
  paper_age_days: number;
}


export interface PaperSubmitPayload {
  arxiv_id?: string;
  source_url?: string;
  title?: string;
  abstract?: string;
  authors?: string[];
  /** Publication date as `YYYY-MM-DD`. */
  date_published?: string;
}

export interface PaperSubmitResponse {
  paper?: Paper | null;
  /** Identifier the frontend should use to build the paper detail URL:
   *  ArXiv ID for ArXiv rows, internal numeric ID otherwise. */
  route_identifier?: string | null;
  /** False when an existing paper was returned instead of creating a new row. */
  created: boolean;
  /** True when an existing arXiv paper was refreshed from arXiv metadata. */
  refreshed?: boolean;
  previous_version?: string | null;
  latest_version?: string | null;
  submission_id?: number | null;
  pending_review?: boolean;
}

/** One bibliography entry to match against the catalog. */
export interface PaperReferenceQuery {
  key: string;
  arxiv_id?: string | null;
  titles?: string[];
}

export interface ResolvedPaperReference {
  key: string;
  matched_by: 'arxiv_id' | 'title' | null;
  paper: Paper | null;
}

export interface PaperLookupResponse {
  references: ResolvedPaperReference[];
}

import type { Paper } from "./papers.types";

export interface UserPreferences {
  /** When true, hide closed-source model rows on benchmark and paper
   *  evaluation tables. */
  hide_closed_source_evals: boolean;
}


export interface BookmarkIdsResponse {
  paper_ids: number[];
}

interface SavedTaskGroup {
  id: number | null;
  slug: string | null;
  name: string;
  papers: Paper[];
}

interface SavedAreaGroup {
  id: number | null;
  name: string;
  tasks: SavedTaskGroup[];
}

export interface SavedPapersResponse {
  count: number;
  areas: SavedAreaGroup[];
  bucket_connected: boolean;
  /** True once any device has migrated this account to its HF Bucket. */
  bucket_migrated: boolean;
}

/** Payload accepted by `POST /papers/submit`. Either `arxiv_id` or
 *  `source_url` must be provided. The remaining fields are optional metadata
 *  overrides used only for external (non-ArXiv) submissions. */

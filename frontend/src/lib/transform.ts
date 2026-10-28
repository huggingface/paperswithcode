/**
 * Backend → UI transform helpers.
 *
 * Every view fetches typed `Paper` / `Task` / `Method` / `Dataset` /
 * `Evaluation` objects from the paper API client and pipes them through these
 * helpers to produce the flat card/detail shapes the components render.
 *
 * `tldr` and `num_pages` schema columns exist but have no ingestion yet — the
 * UI hides those panels when null.
 */

import { format, parseISO } from "date-fns";

import type { LeaderboardRankSummary, Paper, Repository } from "./api/papers.types";
import { assetUrl } from "./apiUrl";

export interface PaperCardProps {
  /** source-aware route id: arxiv_id for ArXiv rows, DB id for external rows */
  id: string;
  /** numeric DB id (used by write APIs) */
  dbId: string;
  title: string;
  abstract: string;
  authors: string[];
  /** Author page IDs parallel to `authors`; feed cards receive them for displayed names. */
  authorIds?: (string | null)[];
  /** Hugging Face profiles parallel to `authorIds`; null for unlinked authors. */
  authorHfProfiles?: ({ username: string; avatarUrl: string | null } | null)[];
  /** paper.tasks[*].slug, used by TagChip */
  tags: string[];
  /** paper.methods[*] reduced to the fields MethodChip needs */
  methods: { id?: string; name: string; slug?: string }[];
  /** Organizations displayed as compact linked logos beside the paper title. */
  organizations: { name: string; slug: string; logoUrl: string | null }[];
  citations: number;
  /** stars for the featured repo; null when no repo */
  github: number | null;
  /** url of the featured repo; null when no repo */
  githubUrl: string | null;
  /** project_pages[0]?.url; null when none */
  project: string | null;
  /** "Apr 26" short label; null when published is null */
  date: string | null;
  /** ISO date string; null when published is null */
  publishedIso: string | null;
  /** ISO publication year, or null */
  year: number | null;
  /** /api/thumbnails url or paper-supplied thumbnail; null otherwise */
  thumbnailUrl: string | null;
  /** Short feed-style TL;DR; null when the paper has none */
  tldr: string | null;
  /** number of arxiv versions; null until version-list is loaded */
  version: string;
  /** /api/v1/papers/trending velocity_24h, when known */
  velocity24h: number | null;
  /** label for the most popular HF artifact category, e.g. "models"; null when none */
  hfKind: "models" | "datasets" | "spaces" | null;
  /** count for the most popular HF artifact category */
  hfCount: number;
  /** link to the most popular HF artifact category; null when none */
  hfUrl: string | null;
  /** Top-3 leaderboard placements, deduped by benchmark and sorted by rank.
   *  Powers the SOTA/#2/#3 badges between the abstract and the tags. */
  sotaRanks: SotaRank[];
}

const HF_KIND_LABELS: Record<string, "models" | "datasets" | "spaces"> = {
  model: "models",
  dataset: "datasets",
  space: "spaces",
};

function summarizeHfArtifacts(paper: Paper): {
  hfKind: "models" | "datasets" | "spaces" | null;
  hfCount: number;
  hfUrl: string | null;
} {
  const summary = paper.hf_artifact_summary;
  if (!summary || !summary.best_kind || !summary.best_url || summary.best_count <= 0) {
    return { hfKind: null, hfCount: 0, hfUrl: null };
  }
  return {
    hfKind: HF_KIND_LABELS[summary.best_kind] ?? null,
    hfCount: summary.best_count,
    hfUrl: summary.best_url,
  };
}

/**
 * Pick the single repository represented by the `Code` CTA and paper-card
 * GitHub stats. Official repos take priority; if none exist, fall back to the
 * most-starred linked repo.
 */
export function summarizeRepos(repos: Repository[] | undefined): {
  github: number | null;
  githubUrl: string | null;
  velocity24h: number | null;
} {
  if (!repos || repos.length === 0) {
    return { github: null, githubUrl: null, velocity24h: null };
  }
  const official = repos.filter((r) => r.is_official);
  const pool = official.length > 0 ? official : repos;
  const top = [...pool].sort((a, b) => (b.num_stars || 0) - (a.num_stars || 0))[0];
  return {
    github: top && top.num_stars > 0 ? top.num_stars : null,
    githubUrl: top?.url || null,
    velocity24h: top?.trending_score ?? null,
  };
}

function shortDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  try {
    const d = typeof iso === "string" ? parseISO(iso) : (iso as Date);
    return format(d, "MMM d, yyyy");
  } catch {
    return null;
  }
}

function isoYear(iso: string | null | undefined): number | null {
  if (!iso) return null;
  try {
    return parseISO(iso).getFullYear();
  } catch {
    return null;
  }
}

/**
 * Turn a backend `Paper` into the props the `PaperCard` component needs.
 */

/** A top-3 leaderboard placement rendered as a SOTA / #2 / #3 badge. */
export interface SotaRank {
  name: string;
  /** Benchmark leaderboard with this paper's evaluation row highlighted. */
  href: string | null;
  rank: number;
}

export function toSotaRanks(ranks: LeaderboardRankSummary[] | null | undefined): SotaRank[] {
  return (ranks || [])
    .filter((r) => r.best_rank >= 1 && r.best_rank <= 3)
    .map((r) => {
      let href: string | null = null;
      if (r.dataset_slug) {
        const query = new URLSearchParams();
        if (r.task_slug) query.set("task", r.task_slug);
        query.set("eval", r.evaluation_id);
        href = `/benchmark/${r.dataset_slug}?${query}`;
      }
      return { name: r.dataset_name, href, rank: r.best_rank };
    });
}

export function transformPaperForCard(paper: Paper): PaperCardProps {
  const { github, githubUrl, velocity24h } = summarizeRepos(paper.repositories);
  const { hfKind, hfCount, hfUrl } = summarizeHfArtifacts(paper);
  const tags = (paper.tasks || []).map((t) => t.slug || "").filter(Boolean);
  const methods = (paper.methods || []).map((m) => ({
    id: m.id,
    name: m.name,
    slug: m.slug,
  }));
  const sotaRanks = toSotaRanks(paper.leaderboard_ranks);
  return {
    id: paper.arxiv_id || paper.id,
    dbId: paper.id,
    title: paper.title,
    abstract: paper.abstract || "",
    authors: paper.authors || [],
    authorIds: (paper.author_links || []).map((link) => link.id ?? null),
    authorHfProfiles: (paper.author_links || []).map((link) =>
      link.hf_username ? { username: link.hf_username, avatarUrl: link.hf_avatar_url ?? null } : null,
    ),
    tags,
    methods,
    organizations: (paper.organizations || []).map((organization) => ({
      name: organization.name,
      slug: organization.slug,
      logoUrl: assetUrl(organization.logo_url) || null,
    })),
    citations: paper.citation_count || 0,
    github,
    githubUrl,
    project: paper.project_pages?.[0]?.url || null,
    date: shortDate(paper.published),
    publishedIso: paper.published || null,
    year: isoYear(paper.published),
    thumbnailUrl: assetUrl(paper.thumbnail_url) || null,
    tldr: paper.tldr || null,
    version: paper.version || "v1",
    velocity24h,
    hfKind,
    hfCount,
    hfUrl,
    sotaRanks,
  };
}

export function humanizeSlug(slug: string): string {
  const displayOverride = TASK_DISPLAY_NAMES.get(slug.toLowerCase());
  if (displayOverride) return displayOverride;

  const acronym = slug.toUpperCase();
  if (TASK_ACRONYMS.has(acronym)) return acronym;

  return slug.replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const TASK_ACRONYMS = new Set(["3D", "AI", "OCR"]);
const TASK_DISPLAY_NAMES = new Map([
  ["3d-tracking", "3D Tracking"],
  ["point-tracking", "2D Point Tracking"],
  ["3d-generation", "3D generation"],
  ["3d-understanding", "3D understanding"],
  ["3d-semantic-segmentation", "3D semantic segmentation"],
  ["3d-instance-segmentation", "3D instance segmentation"],
  ["3d-object-detection", "3D object detection"],
  ["text-to-sql", "Text-to-SQL"],
]);

export function displayTaskName(name?: string, slug?: string): string {
  const label = name || humanizeSlug(slug || "");
  const displayOverride = TASK_DISPLAY_NAMES.get(slug?.toLowerCase() || taskKey(label));
  if (displayOverride) return displayOverride;

  const normalizedSlug = slug?.toUpperCase();
  const normalizedLabel = label.toUpperCase();
  const isAcronymLabel = /^[A-Z0-9][A-Z0-9-]{1,}$/.test(label);

  if (
    isAcronymLabel ||
    (normalizedSlug && TASK_ACRONYMS.has(normalizedSlug)) ||
    TASK_ACRONYMS.has(normalizedLabel)
  ) {
    return normalizedLabel;
  }

  // Title-case each word, but keep words the name already writes in capitals
  // (PII, LLM, VQA) as well as the known acronyms.
  return label.replace(/\b[A-Za-z0-9]+\b/g, (token) => {
    if (/^[A-Z0-9]{2,}$/.test(token) || TASK_ACRONYMS.has(token.toUpperCase())) {
      return token.toUpperCase();
    }
    return token.charAt(0).toUpperCase() + token.slice(1).toLowerCase();
  });
}

function taskKey(value: string): string {
  return value.trim().toLowerCase().replace(/[\s_]+/g, "-");
}

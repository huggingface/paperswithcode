import type { Paper } from "./api/papers.types";
import type { HuggingFaceRepoCounts } from "@/hooks/useHuggingFaceRepos";
import { copyableLeaderboardRanks } from "./leaderboardBadges";
import { safeExternalHref } from "./safeExternalHref";
import { summarizeRepos } from "./transform";
import { stripArxivVersion } from "./utils";

export interface HuggingFaceArtifactsViewer {
  isLoading: boolean;
  paperHref: string | null;
  rows: Array<{
    label: string;
    href: string;
    count: number | undefined;
    isLimited?: boolean;
    links?: Array<{ label: string; href: string }>;
  }>;
  footer: string | null;
}

// Label Hub links by their repo id ("owner/name"): mirrors and demos often
// reuse the official repo name, so the name alone reads like a duplicate.
function resourceLabel(url: string, fallback: string): string {
  try {
    const parsed = new URL(url);
    const segments = parsed.pathname.split("/").filter(Boolean);
    if (segments[0] === "datasets" || segments[0] === "spaces") segments.shift();
    return segments.slice(0, 2).join("/") || parsed.hostname.replace(/^www\./, "");
  } catch {
    return fallback;
  }
}

function artifactLinks(
  explicit: string[],
  discovered: string[] | undefined,
  fallbackLabel: string,
) {
  return [...new Set([...explicit, ...(discovered ?? [])])].map((href) => ({
    href,
    label: resourceLabel(href, fallbackLabel),
  }));
}

function artifactCount(
  explicitUrls: string[],
  discoveredUrls: string[] | undefined,
  discoveredCount: number | undefined,
): number | undefined {
  if (discoveredCount == null && explicitUrls.length === 0 && !discoveredUrls?.length) {
    return undefined;
  }
  const uniqueUrls = new Set([...explicitUrls, ...(discoveredUrls ?? [])]);
  return Math.max(uniqueUrls.size, discoveredCount ?? 0);
}

function knownCount(live: number | undefined, stored: number | undefined): number | undefined {
  if (live == null && stored == null) return undefined;
  return Math.max(live ?? 0, stored ?? 0);
}

function artifactGroupHref(urls: string[]): string {
  return urls[0] ?? "https://huggingface.co";
}

function artifactRowHref(fallbackHref: string, explicitUrls: string[]): string {
  return explicitUrls[0] ?? fallbackHref;
}

function citationFor(paper: Paper) {
  const truncatedTitle = `${paper.title.slice(0, 60)}${paper.title.length > 60 ? "…" : ""}`;
  const displayAuthor = `${paper.authors[0] || ""}${paper.authors.length > 1 ? " et al." : ""}`;
  const fullAuthors = paper.authors.join(" and ");
  const year = (paper.published || "").slice(0, 4) || "—";
  const build = (title: string, authorField: string) => paper.arxiv_id
    ? `@article{${paper.arxiv_id.replace(".", "")},
  title={{${title}}},
  author=${authorField},
  year={{${year}}},
  eprint={{${paper.arxiv_id}}},
  archivePrefix={{arXiv}}
}`
    : `@misc{paper${paper.id},
  title={{${title}}},
  author=${authorField},
  year={{${year}}},
  url={{${paper.source_url || paper.url_abs || ""}}}
}`;
  return {
    citationDisplay: build(truncatedTitle, `{{${displayAuthor}}}`),
    citationCopy: build(paper.title, `{${fullAuthors}}`),
  };
}

export function buildPaperDetailPresentation(
  paper: Paper,
  hfRepos: HuggingFaceRepoCounts | undefined,
  hfLoading: boolean,
) {
  const explicitHfArtifacts = {
    models: paper.hf_models ?? [],
    datasets: paper.hf_datasets ?? [],
    spaces: paper.hf_spaces ?? [],
  };
  // The live Hub lookup can fail (rate limits, outages), so the links and
  // counts stored by the HF sync keep the card populated without it.
  const stored = paper.linked_hf_artifacts;
  const summary = paper.hf_artifact_summary;
  const discoveredHfArtifacts = {
    models: [...(hfRepos?.modelUrls ?? []), ...(stored?.models ?? [])],
    datasets: [...(hfRepos?.datasetUrls ?? []), ...(stored?.datasets ?? [])],
    spaces: [...(hfRepos?.spaceUrls ?? []), ...(stored?.spaces ?? [])],
  };
  const discoveredCounts = {
    models: knownCount(hfRepos?.models, summary?.model_count),
    datasets: knownCount(hfRepos?.datasets, summary?.dataset_count),
    spaces: knownCount(hfRepos?.spaces, summary?.space_count),
  };
  const links = {
    models: artifactLinks(explicitHfArtifacts.models, discoveredHfArtifacts.models, "Model"),
    datasets: artifactLinks(explicitHfArtifacts.datasets, discoveredHfArtifacts.datasets, "Dataset"),
    spaces: artifactLinks(explicitHfArtifacts.spaces, discoveredHfArtifacts.spaces, "Space"),
  };
  const allHfArtifactUrls = {
    models: links.models.map(({ href }) => href),
    datasets: links.datasets.map(({ href }) => href),
    spaces: links.spaces.map(({ href }) => href),
  };
  const canonicalArxivId = paper.arxiv_id != null ? stripArxivVersion(paper.arxiv_id) : null;
  const hfArtifactViewer: HuggingFaceArtifactsViewer = paper.arxiv_id
    ? {
        isLoading: hfLoading,
        paperHref: `https://huggingface.co/papers/${canonicalArxivId}`,
        rows: [
          {
            label: "Models",
            href: artifactRowHref(`https://huggingface.co/models?other=arxiv:${paper.arxiv_id}`, explicitHfArtifacts.models),
            count: artifactCount(explicitHfArtifacts.models, discoveredHfArtifacts.models, discoveredCounts.models),
            isLimited: hfRepos?.isLimited,
            links: links.models,
          },
          {
            label: "Datasets",
            href: artifactRowHref(`https://huggingface.co/datasets?other=arxiv:${paper.arxiv_id}`, explicitHfArtifacts.datasets),
            count: artifactCount(explicitHfArtifacts.datasets, discoveredHfArtifacts.datasets, discoveredCounts.datasets),
            isLimited: hfRepos?.isLimited,
            links: links.datasets,
          },
          {
            label: "Spaces",
            href: artifactRowHref(`https://huggingface.co/papers/${canonicalArxivId}`, explicitHfArtifacts.spaces),
            count: artifactCount(explicitHfArtifacts.spaces, discoveredHfArtifacts.spaces, discoveredCounts.spaces),
            isLimited: hfRepos?.isLimited,
            links: links.spaces,
          },
        ],
        footer: `Cite arxiv.org/abs/${canonicalArxivId} in a HF README to link it here.`,
      }
    : {
        isLoading: false,
        paperHref: null,
        rows: [
          { label: "Models", href: artifactGroupHref(explicitHfArtifacts.models), count: explicitHfArtifacts.models.length, links: links.models },
          { label: "Datasets", href: artifactGroupHref(explicitHfArtifacts.datasets), count: explicitHfArtifacts.datasets.length, links: links.datasets },
          { label: "Spaces", href: artifactGroupHref(explicitHfArtifacts.spaces), count: explicitHfArtifacts.spaces.length, links: links.spaces },
        ],
        footer: null,
      };

  const introducedMethods = (paper.methods ?? []).filter(({ source_paper_id }) => source_paper_id === paper.id);
  const introducedBenchmarks = paper.introduced_benchmarks ?? [];
  const introducedFrameworks = paper.introduced_frameworks ?? [];
  const introducedKinds = [
    introducedMethods.length && (introducedMethods.length === 1 ? "this method" : "these methods"),
    introducedBenchmarks.length && (introducedBenchmarks.length === 1 ? "this benchmark" : "these benchmarks"),
    introducedFrameworks.length && (introducedFrameworks.length === 1 ? "this framework" : "these frameworks"),
  ].filter((value): value is string => Boolean(value));

  return {
    ...citationFor(paper),
    allHfArtifactUrls,
    authorEntries: paper.authors.map((name, index) => ({
      name,
      id: paper.author_links?.[index]?.id ?? null,
      hf_username: paper.author_links?.[index]?.hf_username ?? null,
      hf_avatar_url: paper.author_links?.[index]?.hf_avatar_url ?? null,
    })),
    copyableRanks: copyableLeaderboardRanks(paper.leaderboard_ranks),
    hasIntroducedItems: introducedKinds.length > 0,
    hasLineageItems: Boolean(paper.predecessor_papers?.length || paper.successor_papers?.length),
    hfArtifactViewer,
    hfPaperExists: Boolean(hfRepos?.paperExists),
    introducedBenchmarks,
    introducedFrameworks,
    introducedMethods,
    introducedSummary: introducedKinds.join(" and "),
    numPages: paper.num_pages || null,
    paperSourceLabel: paper.arxiv_id ? `arXiv:${paper.arxiv_id}` : "External resource",
    predecessorPapers: paper.predecessor_papers ?? [],
    projectPages: paper.project_pages?.filter(({ url }) => url).map((page) => ({
      ...page,
      safeHref: safeExternalHref(page.url),
    })) ?? [],
    repoSummary: summarizeRepos(paper.repositories),
    safeAbstractUrl: safeExternalHref(paper.url_abs),
    safeConferenceUrl: safeExternalHref(paper.conference_url_abs),
    safePdfUrl: safeExternalHref(paper.url_pdf),
    successorPapers: paper.successor_papers ?? [],
  };
}

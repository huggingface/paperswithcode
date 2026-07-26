import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { Icon, MethodChip, PaperPreview, SotaBadges, TagChip } from "@/components";
import ClosedSourceEvalBadge from "@/components/ClosedSourceEvalBadge";
import ExternalSourceEvalBadge from "@/components/ExternalSourceEvalBadge";
import LatexTitle, { LatexText } from "@/components/LatexTitle";
import { apiClient, indexPaperFromArxiv } from "@/lib/api";
import type { Paper } from "@/lib/api";
import { apiUrl, assetUrl } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";
import { summarizeRepos } from "@/lib/transform";
import { formatPageTitle, DEFAULT_SITE_SUFFIX } from "@/lib/latexPlainText";
import { formatMetricValue, normalizePaperRouteId } from "@/lib/utils";
import { copyableLeaderboardRanks, leaderboardBadgeMarkdown } from "@/lib/leaderboardBadges";
import { usePaper } from "@/hooks/usePapers";
import { useEvaluationsByPaper } from "@/hooks/useEvaluations";
import { usePreferences } from "@/lib/preferencesContext";
import { useHuggingFaceRepos } from "@/hooks/useHuggingFaceRepos";
import { usePaperEditState } from "@/hooks/usePaperEditState";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import { EditTasksDialog } from "@/components/paper-detail/EditTasksDialog";
import { EditMethodsDialog } from "@/components/paper-detail/EditMethodsDialog";
import { EditRepositoriesDialog } from "@/components/paper-detail/EditRepositoriesDialog";
import { EditProjectPagesDialog } from "@/components/paper-detail/EditProjectPagesDialog";
import { EditSourceUrlDialog } from "@/components/paper-detail/EditSourceUrlDialog";
import { EditEvaluationsDialog } from "@/components/paper-detail/EditEvaluationsDialog";
import { SignInToEditDialog } from "@/components/paper-detail/SignInToEditDialog";
import { SavePaperButton } from "@/components/paper-detail/SavePaperButton";
import { EditableActionButton } from "@/components/paper-detail/EditableActionButton";
import { CodexAddEvalsDialog } from "@/components/paper-detail/CodexAddEvalsDialog";
import { CodexEnrichPaperDialog } from "@/components/paper-detail/CodexEnrichPaperDialog";
import { isCodexAddEvalsEnabled, isCodexEnrichPaperEnabled } from "@/lib/codexAddEvals";

type EditSection =
  | "tasks"
  | "methods"
  | "results"
  | "repositories"
  | "project-pages"
  | "source-url";

const EDIT_SECTION_LABEL: Record<EditSection, string> = {
  tasks: "tasks",
  methods: "methods",
  results: "evaluation results",
  repositories: "GitHub repositories",
  "project-pages": "project pages",
  "source-url": "source URL",
};

const ABSTRACT_PREVIEW_LEN = 360;
const REPO_PREVIEW_LIMIT = 3;
const HF_LINK_PREVIEW_LIMIT = 3;

const PAPER_SECTION_IDS = ["tldr", "abstract", "tasks", "methods", "results"] as const;
type PaperSectionId = (typeof PAPER_SECTION_IDS)[number];

function parsePaperSectionHash(rawHash: string): {
  section: PaperSectionId | null;
  resultsTaskSlug: string | null;
} {
  if (!rawHash) return { section: null, resultsTaskSlug: null };

  const [sectionPart, queryPart] = rawHash.split("?", 2);
  if (!PAPER_SECTION_IDS.includes(sectionPart as PaperSectionId)) {
    return { section: null, resultsTaskSlug: null };
  }

  const section = sectionPart as PaperSectionId;
  if (section !== "results" || !queryPart) {
    return { section, resultsTaskSlug: null };
  }

  return { section, resultsTaskSlug: new URLSearchParams(queryPart).get("task") };
}

function resultsTaskAnchorId(taskSlug: string): string {
  return `results-task-${taskSlug}`;
}

function resultsTaskHash(taskSlug: string): string {
  return `#results?task=${encodeURIComponent(taskSlug)}`;
}

function PaperSectionRule({
  id,
  label,
  accent,
}: {
  id: PaperSectionId;
  label: string;
  accent?: React.ReactNode;
}) {
  return (
    <div className="section-rule paper-section-anchor" id={id}>
      <span>
        <a href={`#${id}`} className="section-anchor-link">
          {label}
        </a>
      </span>
      {accent}
    </div>
  );
}

function formatLongDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return "—";
  }
}

function formatStars(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function formatResourceLinkLabel(url: string, fallback: string): string {
  try {
    const parsed = new URL(url);
    const parts = parsed.pathname.replace(/\/$/, "").split("/").filter(Boolean);
    const slug = parts.at(-1);
    if (slug) return slug.replace(/[-_]+/g, " ");
    return parsed.hostname.replace(/^www\./, "");
  } catch {
    return fallback;
  }
}

const PaperDetailView: React.FC = () => {
  const { arxivId: rawArxivId } = useParams<{ arxivId: string }>();
  const arxivId = rawArxivId ? normalizePaperRouteId(rawArxivId) : "";
  const navigate = useNavigate();
  const { toast } = useToast();
  const { user } = useAuth();
  // Admins can save edits directly. Linked authors and everyone else go
  // through the pending-edit queue for admin review.
  const isAdmin = user?.is_admin ?? false;
  const isSignedIn = !!user;
  // Show edit affordances to every visitor on the paper page. Signed-out users
  // are routed through a sign-in prompt before they can actually submit.
  const canEditPaper = true;

  const { data: paper, isLoading, error, refetch } = usePaper(arxivId || "", !!arxivId);
  const [secondaryQueriesEnabled, setSecondaryQueriesEnabled] = useState(false);

  useEffect(() => {
    if (!rawArxivId || rawArxivId === arxivId) return;
    const suffix = window.location.search + window.location.hash;
    navigate(`/paper/${arxivId}${suffix}`, { replace: true });
  }, [arxivId, navigate, rawArxivId]);

  useEffect(() => {
    if (!paper?.title) return;
    document.title = formatPageTitle(paper.title);
    return () => {
      document.title = DEFAULT_SITE_SUFFIX;
    };
  }, [paper?.title]);

  useEffect(() => {
    setSecondaryQueriesEnabled(false);
    if (!paper?.id) return;

    const timeoutId = window.setTimeout(() => setSecondaryQueriesEnabled(true), 0);
    return () => window.clearTimeout(timeoutId);
  }, [paper?.id]);

  const { data: hfRepos, isLoading: hfLoading } = useHuggingFaceRepos(
    secondaryQueriesEnabled ? paper?.arxiv_id : undefined,
  );
  const {
    data: evaluations,
    isLoading: evaluationsLoading,
    refetch: refetchEvaluations,
  } = useEvaluationsByPaper(
    paper?.id,
    secondaryQueriesEnabled && !!paper?.id,
  );
  const { preferences } = usePreferences();
  // Rows shown in the read-only Results section honor the user's hide
  // closed-source preference. The admin edit dialog still receives the full
  // unfiltered list so editors can manage every row.
  const visibleEvaluations = useMemo(() => {
    if (!evaluations) return evaluations;
    if (!preferences.hide_closed_source_evals) return evaluations;
    return evaluations.filter((e) => e.is_open !== false);
  }, [evaluations, preferences.hide_closed_source_evals]);
  const explicitHfArtifacts = useMemo(
    () => ({
      models: paper?.hf_models ?? [],
      datasets: paper?.hf_datasets ?? [],
      spaces: paper?.hf_spaces ?? [],
    }),
    [paper?.hf_models, paper?.hf_datasets, paper?.hf_spaces],
  );
  // Combine explicitly linked HF artifacts with those discovered via the Hub
  // arXiv endpoint (deduped), then cap each category to the top few links. The
  // full count stays reachable via the clickable count on each row.
  const hfArtifactLinks = useMemo(() => {
    const buildLinks = (
      explicit: string[],
      discovered: string[] | undefined,
      fallbackLabel: string,
    ) => {
      const seen = new Set<string>();
      const links: Array<{ href: string; label: string }> = [];
      for (const href of [...explicit, ...(discovered ?? [])]) {
        if (seen.has(href)) continue;
        seen.add(href);
        links.push({ href, label: formatResourceLinkLabel(href, fallbackLabel) });
        if (links.length >= HF_LINK_PREVIEW_LIMIT) break;
      }
      return links;
    };
    return {
      models: buildLinks(explicitHfArtifacts.models, hfRepos?.modelUrls, "Model"),
      datasets: buildLinks(explicitHfArtifacts.datasets, hfRepos?.datasetUrls, "Dataset"),
      spaces: buildLinks(explicitHfArtifacts.spaces, hfRepos?.spaceUrls, "Space"),
    };
  }, [
    explicitHfArtifacts.models,
    explicitHfArtifacts.datasets,
    explicitHfArtifacts.spaces,
    hfRepos?.modelUrls,
    hfRepos?.datasetUrls,
    hfRepos?.spaceUrls,
  ]);

  // Group evaluations by task so the results section can show one mini-table
  // per task with a shared heading, instead of repeating the task on every row.
  // The backend returns rows sorted by benchmark popularity (most-evaluated
  // benchmark first); we preserve that order both across groups (insertion
  // order of the Map) and within each group's rows so model variants on the
  // same benchmark stay together.
  const evaluationsByTask = useMemo(() => {
    if (!visibleEvaluations) return [];
    type EvalRow = (typeof visibleEvaluations)[number];
    const groups = new Map<
      string,
      { taskId: string; taskName: string; taskSlug?: string; rows: EvalRow[] }
    >();
    for (const e of visibleEvaluations) {
      const key = e.task_id;
      const existing = groups.get(key);
      if (existing) {
        existing.rows.push(e);
      } else {
        groups.set(key, {
          taskId: key,
          taskName: e.task_name || "—",
          taskSlug: e.task_slug,
          rows: [e],
        });
      }
    }
    return Array.from(groups.values());
  }, [visibleEvaluations]);

  const resultsTaskSlugsKey = useMemo(
    () => evaluationsByTask.map((g) => g.taskSlug ?? "").join("|"),
    [evaluationsByTask],
  );

  // Paper version dropdown (PLAN.md §7.5)
  const versionsQ = useQuery({
    queryKey: ["paper-versions", paper?.arxiv_id],
    queryFn: async () => {
      // Strip any vN suffix to get the canonical id.
      const raw = paper!.arxiv_id!.replace(/v\d+$/, "");
      const resp = await fetch(apiUrl(`/api/v1/papers/arxiv/${raw}/versions`));
      if (!resp.ok) return [] as Paper[];
      return (await resp.json()) as Paper[];
    },
    enabled: secondaryQueriesEnabled && !!paper?.arxiv_id,
    staleTime: 10 * 60 * 1000,
  });

  // Related papers: generation-aware embedding endpoint with server-side task fallback.
  const relatedQ = useQuery({
    queryKey: ["related-papers", paper?.id],
    queryFn: () => apiClient.getRelatedPapers(paper!.arxiv_id || paper!.id, 4),
    enabled: secondaryQueriesEnabled && !!paper?.id,
    staleTime: 10 * 60 * 1000,
  });

  const [abstractExpanded, setAbstractExpanded] = useState(false);
  const [showAllAuthors, setShowAllAuthors] = useState(false);
  const [reposExpanded, setReposExpanded] = useState(false);
  const didScrollToHash = useRef(false);

  useEffect(() => {
    didScrollToHash.current = false;
  }, [arxivId]);

  useEffect(() => {
    let rafId = 0;

    const scrollToHash = (force = false, smooth = false): void => {
      const { section, resultsTaskSlug } = parsePaperSectionHash(window.location.hash.slice(1));
      if (!section) return;
      if (!paper) return;
      if (section === "tldr" && !paper.tldr) return;
      // The Results section renders its tables only after the secondary
      // evaluation query has both started and finished. Wait for that so the
      // section has reached its final height before we scroll to it; otherwise
      // the first load lands on a stale offset (the skeleton) and only a second
      // hashchange click corrects it.
      if (section === "results") {
        if (!secondaryQueriesEnabled) return;
        if (evaluationsLoading) return;
      }
      if (!force && didScrollToHash.current) return;

      let node: HTMLElement | null = null;
      if (section === "results" && resultsTaskSlug) {
        node = document.getElementById(resultsTaskAnchorId(resultsTaskSlug));
        if (!node) {
          const matchingGroup = evaluationsByTask.find((g) => g.taskSlug === resultsTaskSlug);
          if (matchingGroup) {
            // Evaluations loaded but the anchor is not painted yet; retry on next run.
            return;
          }
          node = document.getElementById("results");
        }
      } else {
        node = document.getElementById(section);
      }
      if (!node) return;

      const target = node;
      // Defer one frame so any final layout commit (skeleton -> tables, LaTeX,
      // lazy content above the anchor) has settled before we measure the
      // target's position. Mark the scroll done only once it actually runs.
      rafId = window.requestAnimationFrame(() => {
        didScrollToHash.current = true;
        target.scrollIntoView({ block: "start", behavior: smooth ? "smooth" : "auto" });
      });
    };

    scrollToHash();

    const onHashChange = (): void => {
      didScrollToHash.current = false;
      scrollToHash(true, true);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => {
      window.removeEventListener("hashchange", onHashChange);
      if (rafId) window.cancelAnimationFrame(rafId);
    };
  }, [
    paper,
    paper?.tldr,
    secondaryQueriesEnabled,
    evaluationsLoading,
    resultsTaskSlugsKey,
    evaluationsByTask,
  ]);

  const {
    isEditingTasks,
    setIsEditingTasks,
    isEditingMethods,
    setIsEditingMethods,
    isEditingRepositories,
    setIsEditingRepositories,
    isEditingProjectPages,
    setIsEditingProjectPages,
    isEditingEvaluations,
    setIsEditingEvaluations,
    isEditingSourceUrl,
    setIsEditingSourceUrl,
  } = usePaperEditState();

  const [signInSection, setSignInSection] = useState<EditSection | null>(null);

  // Resolve whether the signed-in HF username matches one of the paper's
  // linked authors. Used to surface "you're an author" copy in the pending
  // edit notice; the backend re-checks this at submission time and records
  // `is_author = true` for future auto-approval rules.
  const isLinkedAuthor = useMemo(() => {
    if (!user || !paper?.author_links) return false;
    const me = user.username.toLowerCase();
    return paper.author_links.some(
      (a) =>
        Boolean(a.hf_username) && a.hf_username!.toLowerCase() === me,
    );
  }, [user, paper?.author_links]);

  // Admins save directly (existing behavior). Everyone else who is signed in
  // submits an edit for admin review.
  const editSubmitMode: "direct" | "pending" = isAdmin ? "direct" : "pending";

  const openEdit = (section: EditSection): void => {
    if (!isSignedIn) {
      setSignInSection(section);
      return;
    }
    switch (section) {
      case "tasks":
        setIsEditingTasks(true);
        return;
      case "methods":
        setIsEditingMethods(true);
        return;
      case "results":
        setIsEditingEvaluations(true);
        return;
      case "repositories":
        setIsEditingRepositories(true);
        return;
      case "project-pages":
        setIsEditingProjectPages(true);
        return;
      case "source-url":
        setIsEditingSourceUrl(true);
        return;
    }
  };

  // Auto-index if missing.
  const [indexState, setIndexState] = useState<"idle" | "indexing">("idle");
  const [indexError, setIndexError] = useState<string | null>(null);
  const [indexErrorHint, setIndexErrorHint] = useState<string | null>(null);

  const handleIndex = async () => {
    if (!arxivId) return;
    setIndexState("indexing");
    setIndexError(null);
    setIndexErrorHint(null);
    try {
      await indexPaperFromArxiv(arxivId);
      toast({ title: "Indexed", description: "Paper added to database." });
      setTimeout(() => refetch(), 1200);
      setIndexState("idle");
    } catch (e) {
      const err = e as { response?: string; message?: string; status?: number };
      let msg = err.message || "Failed to index paper";
      if (err.response) {
        try {
          msg = JSON.parse(err.response).detail || msg;
        } catch {
          msg = err.response;
        }
      }
      setIndexError(msg);
      if (err.status === 429 || err.status === 503) {
        setIndexErrorHint("Try again later after arXiv has lifted the temporary limit.");
      }
      setIndexState("idle");
    }
  };

  const { citationDisplay, citationCopy } = useMemo(() => {
    if (!paper) return { citationDisplay: "", citationCopy: "" };
    const truncatedTitle = `${paper.title.slice(0, 60)}${paper.title.length > 60 ? "…" : ""}`;
    const displayAuthor = `${paper.authors[0] || ""}${paper.authors.length > 1 ? " et al." : ""}`;
    const fullAuthors = paper.authors.join(" and ");
    const year = (paper.published || "").slice(0, 4) || "—";
    const build = (title: string, authorField: string) =>
      paper.arxiv_id
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
  }, [paper]);

  const copyableRanks = useMemo(
    () => copyableLeaderboardRanks(paper?.leaderboard_ranks),
    [paper?.leaderboard_ranks],
  );

  const [citationCopied, setCitationCopied] = useState(false);

  const handleCopyCitation = async () => {
    if (!citationCopy) return;
    try {
      await navigator.clipboard.writeText(citationCopy);
      setCitationCopied(true);
      toast({ title: "Citation copied", description: "BibTeX entry copied to clipboard." });
      window.setTimeout(() => setCitationCopied(false), 1500);
    } catch {
      toast({
        title: "Copy failed",
        description: "Could not access the clipboard. Please copy manually.",
        variant: "destructive",
      });
    }
  };

  const handleCopyLeaderboardBadge = async () => {
    if (!paper) return;
    const paperId = paper.arxiv_id || paper.id;
    const markdown = leaderboardBadgeMarkdown(paperId, copyableRanks);
    if (!markdown) return;
    try {
      await navigator.clipboard.writeText(markdown);
      toast({
        title: "PwC badges copied",
        description: "Each badge links to its highlighted leaderboard row.",
      });
    } catch {
      toast({
        title: "Copy failed",
        description: "Could not access the clipboard. Please try again.",
        variant: "destructive",
      });
    }
  };

  // ── render ───────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="page">
        <Skeleton className="h-12 w-3/4 mb-4" />
        <Skeleton className="h-6 w-1/3 mb-8" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !paper) {
    return (
      <div className="page">
        <div className="breadcrumb">
          <Link to="/papers">Papers</Link>
          <span className="sep">/</span>
          <span style={{ color: "var(--ink)" }}>arXiv:{arxivId}</span>
        </div>
        <h1 className="detail-title">Paper not indexed yet</h1>
        <p style={{ fontFamily: "var(--serif)", color: "var(--ink-soft)", marginTop: 16, maxWidth: 640 }}>
          We don't have <span style={{ fontFamily: "var(--mono)" }}>arXiv:{arxivId}</span> in the database.
          You can index it from arXiv right now.
        </p>
        {indexError && (
          <Alert variant="destructive" className="mt-4 max-w-xl">
            <AlertDescription>
              <div>{indexError}</div>
              {indexErrorHint && <div className="mt-2">{indexErrorHint}</div>}
            </AlertDescription>
          </Alert>
        )}
        <div className="action-row">
          {isAdmin && (
            <button className="action-btn" onClick={handleIndex} disabled={indexState === "indexing"}>
              <Icon name="sparkle" size={12} />
              {indexState === "indexing" ? "Indexing…" : "Index from arXiv"}
            </button>
          )}
          <Button variant="outline" onClick={() => navigate("/papers")}>
            Browse Papers
          </Button>
        </div>
      </div>
    );
  }

  const versions = versionsQ.data || [];
  const repoSummary = summarizeRepos(paper.repositories);
  const sortedRepos = [...(paper.repositories ?? [])].sort((a, b) => {
    const aOff = a.is_official ? 1 : 0;
    const bOff = b.is_official ? 1 : 0;
    if (aOff !== bOff) return bOff - aOff;
    return (b.num_stars || 0) - (a.num_stars || 0);
  });
  const visibleRepos = reposExpanded ? sortedRepos : sortedRepos.slice(0, REPO_PREVIEW_LIMIT);
  const canonicalArxivId = paper.arxiv_id?.replace(/v\d+$/, "") ?? null;
  const hfArtifactViewer = paper.arxiv_id
    ? {
        isLoading: hfLoading,
        paperHref: `https://huggingface.co/papers/${canonicalArxivId}`,
        rows: [
          {
            label: "Models",
            href: hfArtifactRowHref(
              `https://huggingface.co/models?other=arxiv:${paper.arxiv_id}`,
              explicitHfArtifacts.models,
            ),
            count: hfArtifactCount(explicitHfArtifacts.models, hfRepos?.modelUrls, hfRepos?.models),
            isLimited: hfRepos?.isLimited,
            links: hfArtifactLinks.models,
          },
          {
            label: "Datasets",
            href: hfArtifactRowHref(
              `https://huggingface.co/datasets?other=arxiv:${paper.arxiv_id}`,
              explicitHfArtifacts.datasets,
            ),
            count: hfArtifactCount(explicitHfArtifacts.datasets, hfRepos?.datasetUrls, hfRepos?.datasets),
            isLimited: hfRepos?.isLimited,
            links: hfArtifactLinks.datasets,
          },
          {
            label: "Spaces",
            href: hfArtifactRowHref(
              `https://huggingface.co/papers/${canonicalArxivId}`,
              explicitHfArtifacts.spaces,
            ),
            count: hfArtifactCount(explicitHfArtifacts.spaces, hfRepos?.spaceUrls, hfRepos?.spaces),
            isLimited: hfRepos?.isLimited,
            links: hfArtifactLinks.spaces,
          },
        ],
        footer: `Cite arxiv.org/abs/${canonicalArxivId} in a HF README to link it here.`,
      }
    : {
        isLoading: false,
        paperHref: null,
        rows: [
          {
            label: "Models",
            href: hfArtifactGroupHref(explicitHfArtifacts.models),
            count: explicitHfArtifacts.models.length,
            links: hfArtifactLinks.models,
          },
          {
            label: "Datasets",
            href: hfArtifactGroupHref(explicitHfArtifacts.datasets),
            count: explicitHfArtifacts.datasets.length,
            links: hfArtifactLinks.datasets,
          },
          {
            label: "Spaces",
            href: hfArtifactGroupHref(explicitHfArtifacts.spaces),
            count: explicitHfArtifacts.spaces.length,
            links: hfArtifactLinks.spaces,
          },
        ],
        footer: null,
      };
  const tldr = paper.tldr || null;
  const numPages = paper.num_pages || null;
  const abstract = paper.abstract || "";
  const abstractShort = abstract.length > ABSTRACT_PREVIEW_LEN ? abstract.slice(0, ABSTRACT_PREVIEW_LEN) + "…" : abstract;
  const abstractView = abstractExpanded || abstract.length <= ABSTRACT_PREVIEW_LEN ? abstract : abstractShort;
  const introducedMethods = (paper.methods || []).filter((method) => method.source_paper_id === paper.id);
  const introducedBenchmarks = paper.introduced_benchmarks || [];
  const hasIntroducedItems = introducedMethods.length > 0 || introducedBenchmarks.length > 0;
  const paperSourceLabel = paper.arxiv_id ? `arXiv:${paper.arxiv_id}` : "External resource";
  const sourceActionLabel = paper.source === "external" ? "Source page" : "arXiv page";
  const projectPages = paper.project_pages?.filter((page) => page.url) ?? [];
  const introducedSummary = (() => {
    const parts: string[] = [];
    if (introducedMethods.length > 0) {
      parts.push(introducedMethods.length === 1 ? "this method" : "these methods");
    }
    if (introducedBenchmarks.length > 0) {
      parts.push(introducedBenchmarks.length === 1 ? "this benchmark" : "these benchmarks");
    }
    if (parts.length === 0) return "";
    if (parts.length === 1) return parts[0];
    return parts.join(" and ");
  })();

  // Lineage banner: directed predecessor/successor edges from
  // `paper_relations`. A paper may have both at once (e.g. a middle entry
  // in a series); we render both groups inside the same banner with
  // separate eyebrow labels.
  const predecessorPapers = paper.predecessor_papers || [];
  const successorPapers = paper.successor_papers || [];
  const hasLineageItems = predecessorPapers.length > 0 || successorPapers.length > 0;

  const AUTHOR_LIMIT = 12;
  const authorEntries = paper.authors.map((name, i) => ({
    name,
    hf_username: paper.author_links?.[i]?.hf_username ?? null,
  }));
  const visibleAuthors =
    showAllAuthors || authorEntries.length <= AUTHOR_LIMIT ? authorEntries : authorEntries.slice(0, AUTHOR_LIMIT);

  return (
    <div className="page">
      <div className="breadcrumb">
        <Link to="/">Trending</Link>
        <span className="sep">/</span>
        <span>{paperSourceLabel}</span>
      </div>

      <div className="detail-grid">
        <div>
          <div className="detail-hero">
            <div className="detail-hero-main">
          <h1 className="detail-title">
            <LatexTitle title={paper.title} />
          </h1>
          <div className="detail-meta">
            <span>{paperSourceLabel}</span>
            <span>·</span>
            <span>Submitted {formatLongDate(paper.published)}</span>
            {numPages && (
              <>
                <span>·</span>
                <span>{numPages} pages</span>
              </>
            )}
            {paper.citation_count != null && (
              <>
                <span>·</span>
                <span>{paper.citation_count.toLocaleString()} citations</span>
              </>
            )}
            {(paper.proceeding || paper.conference_slug) && (
              <>
                <span>·</span>
                {paper.conference_slug ? (
                  <a
                    href={`/conferences/${paper.conference_slug}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: "var(--accent-text)" }}
                  >
                    {(paper.proceeding || paper.conference_name || "").replace(/\s+\d{1,2}$/, "")}
                  </a>
                ) : (
                  <span>{paper.proceeding!.replace(/\s+\d{1,2}$/, "")}</span>
                )}
              </>
            )}
            {versions.length > 1 && (
              <>
                <span>·</span>
                <select
                  className="version-select"
                  value={paper.version}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (!paper.arxiv_id) return;
                    navigate(`/paper/${paper.arxiv_id.replace(/v\d+$/, "")}${v ? `?version=${v}` : ""}`);
                  }}
                >
                  {versions.map((v) => (
                    <option key={v.version} value={v.version}>
                      {v.version} — {formatLongDate(v.published)}
                    </option>
                  ))}
                </select>
              </>
            )}
          </div>
          <div className="detail-authors">
            {visibleAuthors.map((a, i) => (
              <React.Fragment key={i}>
                {a.hf_username ? (
                  <a
                    href={`https://huggingface.co/${a.hf_username}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={`@${a.hf_username} on Hugging Face`}
                  >
                    {a.name}
                  </a>
                ) : (
                  <a>{a.name}</a>
                )}
                {i < visibleAuthors.length - 1 ? ", " : ""}
              </React.Fragment>
            ))}
            {paper.authors.length > AUTHOR_LIMIT && (
              <button
                className="show-more-authors"
                onClick={() => setShowAllAuthors((v) => !v)}
                style={{
                  marginLeft: 8,
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--accent-text)",
                  fontFamily: "var(--mono)",
                  fontSize: 12,
                }}
              >
                {showAllAuthors ? "show fewer" : `+${paper.authors.length - AUTHOR_LIMIT} more`}
              </button>
            )}
          </div>

          <div className="action-row">
            {paper.url_pdf && (
              <a className="action-btn" href={paper.url_pdf} target="_blank" rel="noopener noreferrer">
                <Icon name="pdf" size={12} /> View PDF
              </a>
            )}
            {paper.url_abs && (
              <EditableActionButton
                showEdit={paper.source === "external" && canEditPaper}
                onEdit={() => openEdit("source-url")}
                editAriaLabel="Edit source URL"
              >
                <a
                  className={
                    paper.source === "external" && canEditPaper
                      ? "action-btn-segment action-btn-main"
                      : "action-btn"
                  }
                  href={paper.url_abs}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Icon name="external" size={12} /> {sourceActionLabel}
                </a>
              </EditableActionButton>
            )}
            {hfArtifactViewer.paperHref && hfRepos?.paperExists && (
              <a
                className="bm-action-btn"
                href={hfArtifactViewer.paperHref}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="View on Hugging Face"
              >
                View on <span aria-hidden="true">🤗</span>
              </a>
            )}
            {repoSummary.githubUrl && (
              <EditableActionButton
                showEdit={canEditPaper}
                onEdit={() => openEdit("repositories")}
                editAriaLabel="Edit code repositories"
              >
                <a
                  className={
                    canEditPaper ? "action-btn-segment action-btn-main" : "action-btn"
                  }
                  href={repoSummary.githubUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Icon name="github" size={12} /> Code
                  {repoSummary.github != null && (
                    <span style={{ opacity: 0.7, marginLeft: 4 }}>· {formatStars(repoSummary.github)} ★</span>
                  )}
                </a>
              </EditableActionButton>
            )}
            {canEditPaper && !repoSummary.githubUrl ? (
              <button
                type="button"
                className="action-btn"
                onClick={() => openEdit("repositories")}
                title="Add GitHub repository"
              >
                <Icon name="github" size={12} /> Add code
              </button>
            ) : null}
            {projectPages.length === 1 ? (
              <EditableActionButton
                showEdit={canEditPaper}
                onEdit={() => openEdit("project-pages")}
                editAriaLabel="Edit project pages"
              >
                <a
                  className={
                    canEditPaper ? "action-btn-segment action-btn-main" : "action-btn"
                  }
                  href={projectPages[0].url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Icon name="globe" size={12} /> Project page
                </a>
              </EditableActionButton>
            ) : null}
            {projectPages.length > 1 ? (
              <EditableActionButton
                showEdit={canEditPaper}
                onEdit={() => openEdit("project-pages")}
                editAriaLabel="Edit project pages"
              >
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className={
                        canEditPaper ? "action-btn-segment action-btn-main" : "action-btn"
                      }
                    >
                      <Icon name="globe" size={12} /> Project page
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="project-page-menu">
                    {projectPages.map((page, index) => (
                      <DropdownMenuItem key={page.url} asChild>
                        <a href={page.url} target="_blank" rel="noopener noreferrer">
                          {formatResourceLinkLabel(page.url, `Project page ${index + 1}`)}
                        </a>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              </EditableActionButton>
            ) : null}
            {canEditPaper && projectPages.length === 0 && isSignedIn ? (
              <button
                type="button"
                className="action-btn"
                onClick={() => openEdit("project-pages")}
                title="Add project page"
              >
                <Icon name="globe" size={12} /> Add project page
              </button>
            ) : null}
            {paper.conference_url_abs && (
              <a className="action-btn" href={paper.conference_url_abs} target="_blank" rel="noopener noreferrer">
                <Icon name="external" size={12} /> Conference
              </a>
            )}
            {(paper.organizations || []).map((o) => (
              <Link
                key={o.id}
                to={`/${o.slug}`}
                className="action-btn"
                title={o.name}
                aria-label={o.name}
              >
                {o.logo_url && (
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      height: 16,
                      width: 16,
                      borderRadius: 3,
                      overflow: "hidden",
                    }}
                  >
                    <img
                      src={o.logo_url}
                      alt=""
                      style={{ height: "150%", width: "150%", objectFit: "contain" }}
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                      }}
                    />
                  </span>
                )}
                {o.name}
              </Link>
            ))}
            {isAdmin && isCodexEnrichPaperEnabled() && (
              <CodexEnrichPaperDialog
                paperId={paper.id}
                paperTitle={paper.title}
                onComplete={() => void refetch()}
              />
            )}
            <SavePaperButton paperId={paper.id} />
          </div>

          {paper.leaderboard_ranks && paper.leaderboard_ranks.length > 0 && (
            <SotaBadges
              wrap
              paperHref={`/paper/${paper.arxiv_id || paper.id}`}
              ranks={paper.leaderboard_ranks
                .filter((r) => r.best_rank >= 1 && r.best_rank <= 3)
                .map((r) => ({
                  name: r.dataset_name,
                  slug: r.dataset_slug || null,
                  rank: r.best_rank,
                }))}
            />
          )}
            </div>

            <div className="detail-hero-thumb detail-thumb-wrap">
              <PaperPreview
                paperId={paper.arxiv_id || paper.id}
                title={paper.title}
                thumbnailUrl={assetUrl(paper.thumbnail_url)}
                priority
              />
            </div>
          </div>

          {hasIntroducedItems && (
            <div className="introduced-banner">
              <span className="introduced-label">Introduced</span>
              <div className="introduced-methods">
                {introducedMethods.map((m) => (
                  <button
                    key={`method-${m.id}`}
                    type="button"
                    className="introduced-pill"
                    onClick={() => navigate(`/methods/${m.slug || m.id}`)}
                  >
                    {m.name}
                    <span className="introduced-arrow">→</span>
                  </button>
                ))}
                {introducedBenchmarks.map((b) => (
                  <button
                    key={`benchmark-${b.id}`}
                    type="button"
                    className="introduced-pill"
                    onClick={() => navigate(`/benchmark/${b.slug || b.id}`)}
                  >
                    {b.name}
                    <span className="introduced-arrow">→</span>
                  </button>
                ))}
              </div>
              <span className="introduced-note">
                This paper is the canonical source for {introducedSummary}.
              </span>
            </div>
          )}

          {hasLineageItems && (
            <div className="introduced-banner lineage-banner">
              {successorPapers.length > 0 && (
                <div className="lineage-row">
                  <span className="introduced-label lineage-label">
                    {successorPapers.length === 1 ? "Follow-up paper" : "Follow-up papers"}
                  </span>
                  <div className="introduced-methods">
                    {successorPapers.map((p) => (
                      <button
                        key={`successor-${p.id}`}
                        type="button"
                        className="introduced-pill lineage-pill"
                        onClick={() => navigate(`/paper/${p.route_identifier}`)}
                      >
                        <LatexTitle title={p.title} />
                        <span className="introduced-arrow">→</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {predecessorPapers.length > 0 && (
                <div className="lineage-row">
                  <span className="introduced-label lineage-label">
                    {predecessorPapers.length === 1 ? "Predecessor paper" : "Predecessor papers"}
                  </span>
                  <div className="introduced-methods">
                    {predecessorPapers.map((p) => (
                      <button
                        key={`predecessor-${p.id}`}
                        type="button"
                        className="introduced-pill lineage-pill"
                        onClick={() => navigate(`/paper/${p.route_identifier}`)}
                      >
                        <span className="introduced-arrow lineage-arrow-back">←</span>
                        <LatexTitle title={p.title} />
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {tldr && (
            <>
              <PaperSectionRule id="tldr" label="TL;DR · AI-generated" />
              <div className="tldr-box">{tldr}</div>
            </>
          )}

          <PaperSectionRule id="abstract" label="Abstract" />
          <p className="abstract-text" style={{ marginBottom: 8 }}>
            <LatexText text={abstractView} />
          </p>
          {abstract.length > ABSTRACT_PREVIEW_LEN && (
            <div className="read-full" onClick={() => setAbstractExpanded((v) => !v)}>
              {abstractExpanded ? "− collapse abstract" : "+ read full abstract"}
            </div>
          )}

          <PaperSectionRule
            id="tasks"
            label="Tasks"
            accent={
              <span className="accent">
                {paper.tasks?.length || 0} tagged
                {canEditPaper && (
                  <button
                    type="button"
                    onClick={() => openEdit("tasks")}
                    className="edit-link"
                  >
                    edit
                  </button>
                )}
              </span>
            }
          />
          <div className="paper-tags" style={{ marginBottom: 8 }}>
            {(paper.tasks || []).map((t) => (
              <TagChip key={t.id} slug={t.slug || ""} label={t.name} />
            ))}
          </div>

          <PaperSectionRule
            id="methods"
            label="Methods"
            accent={
              <span className="accent">
                {paper.methods?.length || 0} used
                {canEditPaper && (
                  <button
                    type="button"
                    onClick={() => openEdit("methods")}
                    className="edit-link"
                  >
                    edit
                  </button>
                )}
              </span>
            }
          />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
            {(paper.methods || []).map((m) => (
              <MethodChip key={m.id} method={m} />
            ))}
          </div>

          <PaperSectionRule
            id="results"
            label="Results"
            accent={
              <span className="accent">
                {visibleEvaluations?.length || 0} benchmarks
                {copyableRanks.length > 0 && (
                  <button
                    type="button"
                    className="edit-link results-badge-copy"
                    onClick={handleCopyLeaderboardBadge}
                    title="Copy live leaderboard badges for your repository README"
                  >
                    <Icon name="copy" size={10} /> Copy PwC badge
                  </button>
                )}
                {isAdmin && isCodexAddEvalsEnabled() && (
                  <CodexAddEvalsDialog
                    paperId={paper.id}
                    paperTitle={paper.title}
                    onComplete={() => void refetchEvaluations()}
                  />
                )}
                {canEditPaper && (
                  <button
                    type="button"
                    onClick={() => openEdit("results")}
                    className="edit-link"
                  >
                    edit
                  </button>
                )}
              </span>
            }
          />
          {evaluationsLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : evaluationsByTask.length > 0 ? (
            evaluationsByTask.map((group) => (
              <div
                key={group.taskId}
                className={group.taskSlug ? "paper-section-anchor" : undefined}
                id={group.taskSlug ? resultsTaskAnchorId(group.taskSlug) : undefined}
              >
                <div className="section-rule">
                  <span>
                    {group.taskSlug ? (
                      <>
                        <Link to={`/tasks/${group.taskSlug}`}>{group.taskName}</Link>
                        <a
                          href={resultsTaskHash(group.taskSlug)}
                          className="section-anchor-link results-task-permalink"
                          aria-label={`Permalink to ${group.taskName} results on this paper`}
                          title="Link to this task's results"
                        >
                          #
                        </a>
                      </>
                    ) : (
                      group.taskName
                    )}
                  </span>
                  <span className="accent">
                    {group.rows.length} {group.rows.length === 1 ? "result" : "results"}
                  </span>
                </div>
                <table className="results-table">
                  <colgroup>
                    <col style={{ width: "28%" }} />
                    <col style={{ width: "28%" }} />
                    <col style={{ width: "14%" }} />
                    <col style={{ width: "12%" }} />
                    <col style={{ width: "8%" }} />
                    <col style={{ width: "10%" }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>Benchmark</th>
                      <th>Model</th>
                      <th>Metric</th>
                      <th>Value</th>
                      <th>Rank</th>
                      <th>Compare</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.rows.map((e) => (
                      <tr key={e.id}>
                        <td className="benchmark">
                          {e.dataset_slug ? (
                            <Link to={`/benchmark/${e.dataset_slug}`}>{e.dataset_name || "—"}</Link>
                          ) : (
                            e.dataset_name || "—"
                          )}
                        </td>
                        <td className="model" title={e.model_name || undefined}>
                          {e.hf_model_url ? (
                            <a
                              href={e.hf_model_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="model-hf-link"
                              title={`Open ${e.model_name || "model"} on Hugging Face`}
                            >
                              {e.model_name || "—"}
                            </a>
                          ) : (
                            e.model_name || "—"
                          )}
                          {e.is_open === false && <ClosedSourceEvalBadge />}
                          {(e.external ?? e.is_external) && (
                            <ExternalSourceEvalBadge sourceUrl={e.source_url || e.external_source_url || e.result_url} />
                          )}
                        </td>
                        <td className="metric">{e.best_metric}</td>
                        <td className="value">{formatMetricValue(e.metrics?.[e.best_metric || ""])}</td>
                        <td className="rank">{e.best_rank != null ? `#${e.best_rank}` : "—"}</td>
                        <td className="compare">
                          {e.dataset_slug && (
                            <Link
                              to={`/benchmark/${e.dataset_slug}?${[
                                e.task_slug ? `task=${encodeURIComponent(e.task_slug)}` : "",
                                `eval=${encodeURIComponent(e.id)}`,
                              ]
                                .filter(Boolean)
                                .join("&")}`}
                            >
                              Compare →
                            </Link>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))
          ) : (
            <p style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-faint)" }}>No benchmark results recorded yet.</p>
          )}

        </div>

        <aside className="detail-sidebar">
          {(sortedRepos.length > 0 || canEditPaper) && (
            <div className="sidebar-card">
              <div className="sidebar-card-title">
                <span>GitHub</span>
                <span className="badge">
                  {sortedRepos.length} repo{sortedRepos.length === 1 ? "" : "s"}
                  {canEditPaper && (
                    <button
                      type="button"
                      onClick={() => openEdit("repositories")}
                      className="edit-link"
                    >
                      edit
                    </button>
                  )}
                </span>
              </div>
              {visibleRepos.map((r) => (
                <a
                  key={r.id}
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="code-line"
                  style={{ textDecoration: "none" }}
                >
                  <span className="code-line-repo">
                    <Icon name="github" size={12} />
                    <span className="code-line-repo-name">
                      {r.owner}/{r.name}
                    </span>
                    {r.is_official && (
                      <span className="code-line-official">· Official</span>
                    )}
                  </span>
                  <span className="code-line-stars">★ {formatStars(r.num_stars)}</span>
                </a>
              ))}
              {sortedRepos.length === 0 && (
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--ink-faint)",
                    padding: "6px 0",
                  }}
                >
                  No GitHub repositories linked yet.
                </div>
              )}
              {sortedRepos.length > REPO_PREVIEW_LIMIT && (
                <button
                  type="button"
                  className="bench-show-more"
                  onClick={() => setReposExpanded((v) => !v)}
                >
                  {reposExpanded
                    ? "− show top 3"
                    : `+ show ${sortedRepos.length - REPO_PREVIEW_LIMIT} more repos`}
                </button>
              )}
            </div>
          )}

          {/* Hugging Face block */}
          <HuggingFaceArtifactsCard viewer={hfArtifactViewer} />

          <div className="sidebar-card">
            <div className="sidebar-card-title">
              <span>Citation</span>
              <button
                type="button"
                className="citation-copy-btn"
                onClick={handleCopyCitation}
                aria-label="Copy citation to clipboard"
                title="Copy citation to clipboard"
              >
                <Icon name="copy" size={11} />
                {citationCopied ? "Copied" : "Copy"}
              </button>
            </div>
            <pre
              style={{
                fontFamily: "var(--mono)",
                fontSize: 10.5,
                lineHeight: 1.5,
                color: "var(--ink-soft)",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                margin: 0,
              }}
            >
              {citationDisplay}
            </pre>
          </div>

          {relatedQ.isLoading && (
            <div className="sidebar-card" aria-busy="true">
              <div className="sidebar-card-title">Related papers</div>
              <div className="related-meta">Finding related work…</div>
            </div>
          )}
          {!relatedQ.isLoading && (relatedQ.data?.length ?? 0) > 0 && (
            <div className="sidebar-card">
              <div className="sidebar-card-title">Related papers</div>
              {relatedQ.data!.map((p) => (
                <Link
                  key={p.id}
                  to={`/paper/${p.arxiv_id || p.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="related-paper"
                  style={{ textDecoration: "none", color: "inherit" }}
                >
                  <div className="related-title">
                    <LatexTitle title={p.title} />
                  </div>
                  <div className="related-meta">
                    <span>{p.arxiv_id ? `arXiv:${p.arxiv_id}` : "External resource"}</span>
                    {p.citation_count != null && (
                      <span>{p.citation_count.toLocaleString()} cites</span>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </aside>
      </div>

      {/* Edit dialogs (direct save for admins, pending submission for everyone else) */}
      <EditTasksDialog
        open={isEditingTasks}
        onOpenChange={setIsEditingTasks}
        paperId={paper.id}
        arxivId={arxivId}
        initialTaskIds={paper.tasks?.map((t) => parseInt(t.id)) || []}
        initialTasks={paper.tasks || []}
        submitMode={editSubmitMode}
        isAuthor={isLinkedAuthor}
      />
      <EditMethodsDialog
        open={isEditingMethods}
        onOpenChange={setIsEditingMethods}
        paperId={paper.id}
        arxivId={arxivId}
        initialMethodIds={paper.methods?.map((m) => parseInt(m.id)) || []}
        initialMethods={paper.methods || []}
        submitMode={editSubmitMode}
        isAuthor={isLinkedAuthor}
      />
      <EditRepositoriesDialog
        open={isEditingRepositories}
        onOpenChange={setIsEditingRepositories}
        paperId={paper.id}
        arxivId={arxivId}
        initialRepositories={
          paper.repositories?.map((r) => ({ url: r.url, is_official: r.is_official || false })) || []
        }
        submitMode={editSubmitMode}
        isAuthor={isLinkedAuthor}
      />
      <EditProjectPagesDialog
        open={isEditingProjectPages}
        onOpenChange={setIsEditingProjectPages}
        paperId={paper.id}
        arxivId={arxivId}
        initialProjectPages={
          paper.project_pages?.map((p) => ({ url: p.url, is_official: p.is_official || false })) || []
        }
        submitMode={editSubmitMode}
        isAuthor={isLinkedAuthor}
      />
      <EditEvaluationsDialog
        open={isEditingEvaluations}
        onOpenChange={setIsEditingEvaluations}
        paperId={paper.id}
        arxivId={arxivId}
        initialEvaluations={evaluations || []}
        paperTasks={paper.tasks || []}
        submitMode={editSubmitMode}
        isAuthor={isLinkedAuthor}
      />
      <EditSourceUrlDialog
        open={isEditingSourceUrl}
        onOpenChange={setIsEditingSourceUrl}
        paperId={paper.id}
        arxivId={arxivId}
        initialUrl={paper.source_url ?? paper.url_abs ?? ""}
        submitMode={editSubmitMode}
        isAuthor={isLinkedAuthor}
      />
      <SignInToEditDialog
        open={signInSection !== null}
        onOpenChange={(open) => {
          if (!open) setSignInSection(null);
        }}
        sectionLabel={
          signInSection ? EDIT_SECTION_LABEL[signInSection] : "this paper"
        }
        returnTo={typeof window !== "undefined" ? window.location.pathname : "/"}
      />
    </div>
  );
};

interface HfRowProps {
  label: string;
  href: string;
  count: number | undefined;
  isLimited?: boolean;
  links?: Array<{ label: string; href: string }>;
}

interface HuggingFaceArtifactsViewer {
  isLoading: boolean;
  paperHref: string | null;
  rows: HfRowProps[];
  footer: string | null;
}

const HuggingFaceArtifactsCard: React.FC<{
  viewer: HuggingFaceArtifactsViewer;
}> = ({ viewer }) => (
  <div className="sidebar-card">
    <div className="sidebar-card-title">
      {viewer.paperHref ? (
        <a
          href={viewer.paperHref}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "inherit", textDecoration: "none" }}
        >
          🤗 Hugging Face
        </a>
      ) : (
        <span>🤗 Hugging Face</span>
      )}
    </div>
    {viewer.isLoading ? (
      <Skeleton className="h-16 w-full" />
    ) : (
      <>
        {viewer.rows.map((row) => (
          <HfRow key={row.label} {...row} />
        ))}
        {viewer.footer && (
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-faint)", marginTop: 12 }}>
            {viewer.footer}
          </div>
        )}
      </>
    )}
  </div>
);

const HfRow: React.FC<HfRowProps> = ({ label, href, count, isLimited, links }) => {
  const hasLinks = (links?.length ?? 0) > 0;
  const countLabel = count != null ? `${count}${isLimited ? "+" : ""}` : "—";
  // Prefer an explicit repo URL when we have one. Otherwise the count links to
  // the aggregate listing on Hugging Face (e.g. models?other=arxiv:<id>) so the
  // full set stays reachable even when only the top few direct links are shown.
  const countNode =
    count ? (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="hf-artifact-count"
      >
        {countLabel}
      </a>
    ) : (
      <span className="hf-artifact-count hf-artifact-count--empty">{countLabel}</span>
    );

  return (
    <div className="hf-artifact-row">
      <div className="hf-artifact-row-header">
        <span>{label}</span>
        {countNode}
      </div>
      {hasLinks && (
        <div className="hf-artifact-links">
          {links!.map((link) => (
            <a key={link.href} href={link.href} target="_blank" rel="noopener noreferrer">
              {link.label}
            </a>
          ))}
        </div>
      )}
    </div>
  );
};

function hfArtifactGroupHref(urls: string[]): string {
  return urls[0] ?? "https://huggingface.co";
}

function hfArtifactRowHref(fallbackHref: string, explicitUrls: string[]): string {
  return explicitUrls[0] ?? fallbackHref;
}

function hfArtifactCount(
  explicitUrls: string[],
  discoveredUrls: string[] | undefined,
  discoveredCount: number | undefined,
): number | undefined {
  if (discoveredCount == null && explicitUrls.length === 0 && !discoveredUrls?.length) return undefined;
  const uniqueUrls = new Set([...explicitUrls, ...(discoveredUrls ?? [])]);
  return Math.max(discoveredCount ?? 0, uniqueUrls.size);
}

export default PaperDetailView;

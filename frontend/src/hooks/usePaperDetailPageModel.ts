import { paperQueryKeys } from "@/lib/paperQueryKeys";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { useToast } from "@/hooks/use-toast";
import { useEvaluationsByPaper } from "@/hooks/useEvaluations";
import { useHuggingFaceRepos } from "@/hooks/useHuggingFaceRepos";
import { usePaper } from "@/hooks/usePapers";
import { evaluationsApi } from "@/lib/api/evaluations";
import { papersApi } from "@/lib/api/papers";
import { formatPageTitle } from "@/lib/latexPlainText";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { usePreferences } from "@/lib/preferences";
import { normalizePaperRouteId, stripArxivVersion } from "@/lib/utils";
import { buildPaperDetailPresentation } from "@/lib/paperDetailPresentation";
import { TEN_MINUTES } from "@/lib/api/queryKeys";

const PAPER_SECTION_IDS = ["tldr", "abstract", "tasks", "methods", "results"] as const;
export type PaperSectionId = (typeof PAPER_SECTION_IDS)[number];

export function parsePaperSectionHash(rawHash: string): {
  section: PaperSectionId | null;
  resultsTaskSlug: string | null;
} {
  if (!rawHash) return { section: null, resultsTaskSlug: null };
  const [sectionPart, queryPart] = rawHash.split("?", 2);
  if (!PAPER_SECTION_IDS.includes(sectionPart as PaperSectionId)) {
    return { section: null, resultsTaskSlug: null };
  }
  const section = sectionPart as PaperSectionId;
  if (section !== "results" || !queryPart) return { section, resultsTaskSlug: null };
  return { section, resultsTaskSlug: new URLSearchParams(queryPart).get("task") };
}

export const resultsTaskAnchorId = (taskSlug: string) => `results-task-${taskSlug}`;
export const resultsTaskHash = (taskSlug: string) =>
  `#results?task=${encodeURIComponent(taskSlug)}`;

interface ConflictRefreshOptions {
  direct: boolean;
  paperId?: string;
  refetchEvaluations: () => unknown;
  refetchPaper: () => unknown;
}

export function refreshAfterCatalogConflict({
  direct,
  paperId,
  refetchEvaluations,
  refetchPaper,
}: ConflictRefreshOptions): void {
  void refetchPaper();
  void refetchEvaluations();
  if (!direct || !paperId) return;
  void papersApi.primeCurationState(paperId, true).catch(() => undefined);
  void evaluationsApi.primeCurationState(paperId, true).catch(() => undefined);
}

export function usePaperDetailPageModel(
  rawArxivId: string | undefined,
  editSubmitMode: "direct" | "pending",
) {
  const arxivId = rawArxivId ? normalizePaperRouteId(rawArxivId) : "";
  const navigate = useNavigate();
  const { toast } = useToast();
  const { preferences } = usePreferences();
  const paperQuery = usePaper(arxivId, Boolean(arxivId));
  const paper = paperQuery.data;
  const [secondaryQueriesEnabled, setSecondaryQueriesEnabled] = useState(false);

  useEffect(() => {
    if (!rawArxivId || rawArxivId === arxivId) return;
    navigate(`/paper/${arxivId}${window.location.search}${window.location.hash}`, {
      replace: true,
    });
  }, [arxivId, navigate, rawArxivId]);

  useDocumentTitle(paper?.title && (paper.page_title || formatPageTitle(paper.title)));

  useEffect(() => {
    setSecondaryQueriesEnabled(false);
    if (!paper?.id) return;
    const timeoutId = window.setTimeout(() => setSecondaryQueriesEnabled(true), 0);
    return () => window.clearTimeout(timeoutId);
  }, [paper?.id]);

  const secondaryReady = secondaryQueriesEnabled && Boolean(paper?.id);
  const hfQuery = useHuggingFaceRepos(
    secondaryQueriesEnabled ? paper?.arxiv_id : undefined,
  );
  const evaluationsQuery = useEvaluationsByPaper(paper?.id, secondaryReady);
  const versionsQuery = useQuery({
    queryKey: [...paperQueryKeys.feeds.versions, paper?.arxiv_id],
    queryFn: () => papersApi.versions(stripArxivVersion(paper!.arxiv_id!)),
    enabled: secondaryReady && Boolean(paper?.arxiv_id),
    staleTime: TEN_MINUTES,
  });
  const relatedQuery = useQuery({
    queryKey: [...paperQueryKeys.feeds.related, paper?.id],
    queryFn: () => papersApi.related(paper!.arxiv_id || paper!.id, 4),
    enabled: secondaryReady,
    staleTime: TEN_MINUTES,
  });

  useEffect(() => {
    const handleConflict = () => {
      refreshAfterCatalogConflict({
        direct: editSubmitMode === "direct",
        paperId: paper?.id,
        refetchEvaluations: evaluationsQuery.refetch,
        refetchPaper: paperQuery.refetch,
      });
      toast({
        title: "This section changed",
        description:
          "The latest state has been reloaded. Review your changes before submitting again.",
        variant: "destructive",
      });
    };
    window.addEventListener("pwc:catalog-conflict", handleConflict);
    return () => window.removeEventListener("pwc:catalog-conflict", handleConflict);
  }, [
    editSubmitMode,
    evaluationsQuery.refetch,
    paper?.id,
    paperQuery.refetch,
    toast,
  ]);

  const visibleEvaluations = useMemo(() => {
    const evaluations = evaluationsQuery.data;
    if (!evaluations || !preferences.hide_closed_source_evals) return evaluations;
    return evaluations.filter((evaluation) => evaluation.is_open !== false);
  }, [evaluationsQuery.data, preferences.hide_closed_source_evals]);

  const evaluationsByTask = useMemo(() => {
    if (!visibleEvaluations) return [];
    type EvaluationRow = (typeof visibleEvaluations)[number];
    const groups = new Map<
      string,
      { taskId: string; taskName: string; taskSlug?: string; rows: EvaluationRow[] }
    >();
    for (const evaluation of visibleEvaluations) {
      const existing = groups.get(evaluation.task_id);
      if (existing) existing.rows.push(evaluation);
      else {
        groups.set(evaluation.task_id, {
          taskId: evaluation.task_id,
          taskName: evaluation.task_name || "—",
          taskSlug: evaluation.task_slug,
          rows: [evaluation],
        });
      }
    }
    return [...groups.values()];
  }, [visibleEvaluations]);

  const presentation = useMemo(
    () => paper ? buildPaperDetailPresentation(paper, hfQuery.data, hfQuery.isLoading) : null,
    [hfQuery.data, hfQuery.isLoading, paper],
  );
  const didScrollToHash = useRef(false);

  useEffect(() => {
    didScrollToHash.current = false;
  }, [arxivId]);

  useEffect(() => {
    let frameId = 0;
    const scrollToHash = (force = false, smooth = false) => {
      const { section, resultsTaskSlug } = parsePaperSectionHash(
        window.location.hash.slice(1),
      );
      if (!section || !paper || (section === "tldr" && !paper.tldr)) return;
      if (section === "results" && (!secondaryReady || evaluationsQuery.isLoading)) return;
      if (!force && didScrollToHash.current) return;

      let target = section === "results" && resultsTaskSlug
        ? document.getElementById(resultsTaskAnchorId(resultsTaskSlug))
        : document.getElementById(section);
      if (!target && section === "results" && resultsTaskSlug) {
        if (evaluationsByTask.some(({ taskSlug }) => taskSlug === resultsTaskSlug)) return;
        target = document.getElementById("results");
      }
      if (!target) return;
      frameId = window.requestAnimationFrame(() => {
        didScrollToHash.current = true;
        target.scrollIntoView({ block: "start", behavior: smooth ? "smooth" : "auto" });
      });
    };

    scrollToHash();
    const onHashChange = () => {
      didScrollToHash.current = false;
      scrollToHash(true, true);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => {
      window.removeEventListener("hashchange", onHashChange);
      if (frameId) window.cancelAnimationFrame(frameId);
    };
  }, [
    evaluationsByTask,
    evaluationsQuery.isLoading,
    paper,
    secondaryReady,
  ]);

  return {
    arxivId,
    evaluations: evaluationsQuery.data,
    evaluationsByTask,
    evaluationsLoading: evaluationsQuery.isLoading,
    paper,
    paperError: paperQuery.error,
    paperLoading: paperQuery.isLoading,
    presentation,
    refetchEvaluations: evaluationsQuery.refetch,
    refetchPaper: paperQuery.refetch,
    relatedQuery,
    versions: versionsQuery.data ?? [],
    visibleEvaluations,
  };
}

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import type { Task } from "@/lib/api/catalog.types";
import type { LeaderboardMetric, MetricDirections } from "@/lib/api/evaluations.types";
import { catalogApi } from "@/lib/api/catalog";
import { evaluationsApi } from "@/lib/api/evaluations";
import { usePreferences } from "@/lib/preferencesContext";
import { formatMetricValue } from "@/lib/utils";
import { selectLeaderboardEvaluations } from "@/lib/leaderboardEvaluations";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Alert, AlertDescription } from "@/components/ui/alert";
import LatexTitle from "@/components/LatexTitle";
import ClosedSourceEvalBadge from "@/components/ClosedSourceEvalBadge";
import ExternalSourceEvalBadge from "@/components/ExternalSourceEvalBadge";
import BenchmarkTrendSparkline from "@/components/BenchmarkTrendSparkline";
import BenchmarkChart from "@/components/benchmark/BenchmarkChart";
import CopyScreenshotButton from "@/components/benchmark/CopyScreenshotButton";
import {
  computeSeries,
  evaluationMatchesHighlight,
  filterLeaderboardByParameterCount,
  formatParameterCount,
  mergeLeaderboardEvaluations,
  PARAMETER_FILTERS,
  parseMetricValue,
  parseParameterFilter,
  storedRankForMetric,
} from "@/lib/benchmarkLeaderboard";
import "@/styles/benchmark-detail.css";
import { safeExternalHref } from "@/lib/safeExternalHref";
import { slugify } from "@/lib/slug";

function extractSourcePaperRouteId(paperUrl?: string | null): string | null {
  if (!paperUrl) return null;

  const url = paperUrl.trim();
  const arxivMatch = url.match(/^https?:\/\/(?:www\.)?arxiv\.org\/(?:abs|pdf)\/([^/?#]+)/i);
  if (arxivMatch?.[1]) {
    return arxivMatch[1].replace(/\.pdf$/i, "");
  }

  const localMatch = url.match(/^(?:https?:\/\/(?:www\.)?paperswithcode\.co)?\/paper\/([^/?#]+)/i);
  return localMatch?.[1] ?? null;
}

function renderBenchmarkPaperTitle(
  paperTitle: string | undefined,
  paperLabel: string | null,
): React.ReactNode {
  if (paperTitle) {
    return <LatexTitle title={paperTitle} />;
  }
  return paperLabel || "—";
}

const BenchmarkDetailView: React.FC = () => {
  const { datasetSlug } = useParams<{ datasetSlug: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  // The "See all" button on PaperDetailView's evaluation card links here
  // with `?task=<slug>` so we can keep that task as the breadcrumb context
  // for benchmarks linked to multiple tasks (e.g. COCO val2017).
  const taskSlugFromQuery = searchParams.get("task") || undefined;
  // PaperDetailView's "Compare →" link in the per-paper results table appends
  // `?eval=<evaluationId>` so the leaderboard can spotlight the originating
  // row. The id is stable and unambiguous (model+harness display strings can
  // collide), so we deep-link by it and silently fall back to the normal
  // benchmark page when the id is missing or no longer present.
  const highlightEvalId = searchParams.get("eval") || undefined;
  const parameterBound = parseParameterFilter(searchParams.get("max_parameters_exclusive"));
  const { preferences, setHideClosedSourceEvals } = usePreferences();
  const highlightRowRef = useRef<HTMLTableRowElement | null>(null);
  const didScrollToHighlight = useRef(false);
  const chartCardRef = useRef<HTMLDivElement | null>(null);
  const leaderboardCardRef = useRef<HTMLDivElement | null>(null);
  const [tableScrollElement, setTableScrollElement] = useState<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!tableScrollElement) return;
    const updateOverflow = () => {
      tableScrollElement.classList.toggle(
        "has-horizontal-overflow",
        tableScrollElement.scrollWidth > tableScrollElement.clientWidth,
      );
    };
    const observer = new ResizeObserver(updateOverflow);
    observer.observe(tableScrollElement);
    // Metric expansion changes the table width without resizing its wrapper.
    if (tableScrollElement.firstElementChild) observer.observe(tableScrollElement.firstElementChild);
    updateOverflow();
    return () => observer.disconnect();
  }, [tableScrollElement]);
  const [expandedMetricScope, setExpandedMetricScope] = useState<string | null>(null);
  const metricScope = `${datasetSlug}:${taskSlugFromQuery || ""}`;
  const showMoreMetrics = expandedMetricScope === metricScope;

  // Fetching the dataset with `include_paper=true` collapses the previous
  // dataset → paper waterfall into a single round trip.
  const datasetQ = useQuery({
    queryKey: [
      "dataset",
      datasetSlug,
      "with-paper",
      taskSlugFromQuery,
      preferences.hide_closed_source_evals ? "open" : "all",
    ],
    queryFn: () => catalogApi.getDatasetBySlug(datasetSlug!, {
      include_paper: true,
      task: taskSlugFromQuery,
      is_open: preferences.hide_closed_source_evals ? true : undefined,
    }),
    enabled: !!datasetSlug,
    staleTime: 10 * 60 * 1000,
  });

  // Fetch every evaluation on this dataset once. Metric switching is purely
  // a UI concern (column choice, sort key, SOTA computation), so we must not
  // pass the selected metric as an API filter — the backend filters on the row's
  // `best_metric` column, which would drop rows whose primary metric is
  // different from the tab the user clicked (e.g. an F1-primary row that
  // also carries Recall/Precision values).
  const evalsQ = useQuery({
    queryKey: ["dataset-evals", datasetQ.data?.id],
    queryFn: () => evaluationsApi.byDataset(datasetQ.data!.id),
    enabled: !!datasetQ.data?.id,
    staleTime: 5 * 60 * 1000,
  });

  const datasetTasksQ = useQuery<Task[]>({
    queryKey: ["dataset-tasks", datasetQ.data?.id],
    queryFn: () => catalogApi.datasetTasks(datasetQ.data!.id),
    enabled: !!datasetQ.data?.id,
    staleTime: 10 * 60 * 1000,
  });

  const directionsQ = useQuery<MetricDirections>({
    queryKey: ["metric-directions"],
    queryFn: () => catalogApi.metricDirections(),
    staleTime: 60 * 60 * 1000,
  });

  // When Compare → deep-links with `?eval=<id>`, resolve the originating row
  // so we land on the correct (task, metric) even if `?task=` is missing.
  const highlightEval = useMemo(() => {
    if (!highlightEvalId || !evalsQ.data?.length) return null;
    return evalsQ.data.find((e) => e.id === highlightEvalId) || null;
  }, [highlightEvalId, evalsQ.data]);

  // Pick the (task, dataset) leaderboard whose configured metrics drive the
  // table columns. Prefer `?task=<slug>` (set by PaperDetailView links); for
  // benchmarks with multiple linked tasks but no URL hint, fall back to the
  // task that the most evaluations belong to, so the column set matches the
  // bulk of the data. With zero linked tasks (rare legacy rows) we leave it
  // null and the page falls back to a data-union metric set.
  const currentTaskId = useMemo<string | null>(() => {
    const tasks = datasetTasksQ.data || [];
    if (tasks.length === 0) return null;
    if (highlightEval?.task_id && tasks.some((t) => t.id === highlightEval.task_id)) {
      return highlightEval.task_id;
    }
    if (taskSlugFromQuery) {
      const match = tasks.find((t) => t.slug === taskSlugFromQuery);
      if (match) return match.id;
    }
    if (tasks.length === 1) return tasks[0].id;
    const evals = evalsQ.data || [];
    if (evals.length > 0) {
      const counts = new Map<string, number>();
      for (const e of evals) {
        counts.set(e.task_id, (counts.get(e.task_id) || 0) + 1);
      }
      let topId: string | null = null;
      let topN = -1;
      for (const t of tasks) {
        const n = counts.get(t.id) || 0;
        if (n > topN) {
          topN = n;
          topId = t.id;
        }
      }
      if (topId) return topId;
    }
    return tasks[0].id;
  }, [datasetTasksQ.data, evalsQ.data, taskSlugFromQuery, highlightEval]);

  const benchmarkTrendsQ = useQuery({
    queryKey: [
      "task-benchmark-trends",
      currentTaskId,
      preferences.hide_closed_source_evals ? true : undefined,
    ],
    queryFn: () =>
      catalogApi.trendingBenchmarks(currentTaskId!, {
        limit: 100,
        min_recent_papers: 0,
        is_open: preferences.hide_closed_source_evals ? true : undefined,
      }),
    enabled: !!currentTaskId && !!datasetQ.data?.id,
    staleTime: 10 * 60 * 1000,
  });

  const benchmarkTrend = useMemo(
    () =>
      (benchmarkTrendsQ.data?.results || []).find(
        (benchmark) => benchmark.id === datasetQ.data?.id,
      ) || null,
    [benchmarkTrendsQ.data, datasetQ.data?.id],
  );

  // Configured metrics for the current leaderboard — the canonical column
  // set rendered in the table. Missing for legacy/unconfigured (task,
  // dataset) pairs, in which case we fall back to a data-union below.
  const leaderboardMetricsQ = useQuery<LeaderboardMetric[]>({
    queryKey: ["leaderboard-metrics", datasetQ.data?.id, currentTaskId],
    queryFn: () => catalogApi.leaderboardMetrics(datasetQ.data!.id, currentTaskId!),
    enabled: !!datasetQ.data?.id && !!currentTaskId,
    staleTime: 10 * 60 * 1000,
  });

  // Filter to evaluations on the current (task, dataset) leaderboard so
  // unrelated rows from other tasks don't pollute ranking / chart / column
  // population. Falls back to all evals when no task is resolved.
  const evaluationVisibility = useMemo(
    () => selectLeaderboardEvaluations(
      evalsQ.data,
      currentTaskId,
      preferences.hide_closed_source_evals,
    ),
    [evalsQ.data, currentTaskId, preferences.hide_closed_source_evals],
  );
  const taskEvals = evaluationVisibility.visible;
  const hiddenClosedEvals = evaluationVisibility.hiddenClosed;
  const hiddenClosedTopEval = evaluationVisibility.topHiddenClosed;

  const mergedTaskEvals = useMemo(
    () => mergeLeaderboardEvaluations(taskEvals),
    [taskEvals],
  );

  const displayedLeaderboardEvals = useMemo(
    () => filterLeaderboardByParameterCount(mergedTaskEvals, parameterBound),
    [mergedTaskEvals, parameterBound],
  );

  // Last-resort metric set when this leaderboard has no configured metrics
  // in `task_dataset_metrics` (e.g. legacy imports). Picked over data union
  // only when `configuredMetrics` is empty.
  const dataMetrics = useMemo(() => {
    const set = new Set<string>();
    mergedTaskEvals.forEach((e) => {
      if (e.best_metric) set.add(e.best_metric);
      Object.keys(e.metrics || {}).forEach((k) => set.add(k));
    });
    return Array.from(set);
  }, [mergedTaskEvals]);

  const configuredMetrics = useMemo(
    () => (leaderboardMetricsQ.data || []).map((m) => m.metric_name),
    [leaderboardMetricsQ.data],
  );

  // Full metric set exposed in the View dropdown.
  const allowedMetrics = configuredMetrics.length ? configuredMetrics : dataMetrics;

  // Pick the most useful default metric: whichever metric is set as
  // `best_metric` on the most evaluation rows (so multi-metric leaderboards
  // default to the metric most papers actually rank on). Fall back to the
  // first allowed metric when no eval data is available yet.
  const defaultMetric = useMemo(() => {
    if (mergedTaskEvals.length === 0) return allowedMetrics[0] || "";
    const counts = new Map<string, number>();
    for (const e of mergedTaskEvals) {
      const metric = e.best_metric;
      if (!metric || parseMetricValue(e.metrics?.[metric]) === null) continue;
      if (configuredMetrics.length && !allowedMetrics.includes(metric)) continue;
      counts.set(metric, (counts.get(metric) || 0) + 1);
    }
    let top: string | null = null;
    let topN = 0;
    for (const [m, n] of counts) {
      if (n > topN) {
        topN = n;
        top = m;
      }
    }
    return top || allowedMetrics[0] || mergedTaskEvals[0]?.best_metric || "";
  }, [mergedTaskEvals, allowedMetrics, configuredMetrics]);

  const metricFromQuery = searchParams.get("metric")?.trim();
  const requestedMetric = metricFromQuery
    ? allowedMetrics.find((metric) => metric.toLocaleLowerCase() === metricFromQuery.toLocaleLowerCase())
    : undefined;
  const activeMetric = requestedMetric || highlightEval?.best_metric || defaultMetric;
  const direction = directionsQ.data?.directions?.[activeMetric] || "higher_is_better";
  const arrow: "↑" | "↓" = direction === "lower_is_better" ? "↓" : "↑";

  // Metric ordering shared by the table columns and the View dropdowns. The
  // metric currently shown in the chart (`activeMetric`) leads, so the
  // default/selected metric is always the first metric column; the rest
  // follow in their configured leaderboard order.
  const orderedMetrics = useMemo(() => {
    if (!activeMetric || !allowedMetrics.includes(activeMetric)) return allowedMetrics;
    return [activeMetric, ...allowedMetrics.filter((m) => m !== activeMetric)];
  }, [allowedMetrics, activeMetric]);

  // The selected metric stays visible when additional columns are collapsed.
  const visibleMetrics = useMemo(() => {
    if (orderedMetrics.length === 0) return activeMetric ? [activeMetric] : [];
    return showMoreMetrics ? orderedMetrics : orderedMetrics.slice(0, 1);
  }, [orderedMetrics, activeMetric, showMoreMetrics]);

  const { points: chartPoints, sota, sotaModel } = useMemo(
    () => computeSeries(displayedLeaderboardEvals, activeMetric, arrow),
    [displayedLeaderboardEvals, activeMetric, arrow],
  );
  // Dataset detail embeds a tiny, HTTP-cacheable summary when the URL supplies
  // task context. Render it immediately while the full leaderboard loads, then
  // reconcile with the client-computed result once all dependencies resolve.
  const initialSummary = parameterBound === undefined
    ? datasetQ.data?.leaderboard_summary
    : undefined;
  const isFullSummaryReady =
    evalsQ.isSuccess &&
    datasetTasksQ.isSuccess &&
    directionsQ.isSuccess &&
    (!currentTaskId || leaderboardMetricsQ.isSuccess);
  const displayedMetric = isFullSummaryReady ? activeMetric : initialSummary?.metric;
  const displayedSota = isFullSummaryReady ? sota : initialSummary?.value;
  const displayedSotaModel = isFullSummaryReady
    ? sotaModel
    : initialSummary?.model_name;
  const isSummaryLoading =
    !isFullSummaryReady &&
    !initialSummary;
  const isInitialFilteredViewLoading =
    parameterBound !== undefined && !isFullSummaryReady;

  // Bring the highlighted leaderboard row into view once the evaluations
  // query resolves. Guarded by a ref so subsequent metric switches don't
  // hijack the user's scroll position.
  useEffect(() => {
    if (didScrollToHighlight.current) return;
    if (!highlightEvalId) return;
    if (!evalsQ.data || evalsQ.data.length === 0) return;
    const node = highlightRowRef.current;
    if (!node) return;
    didScrollToHighlight.current = true;
    node.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [highlightEvalId, evalsQ.data]);

  // Breadcrumb task — the resolved `currentTaskId` lifted back to the full
  // Task object so we can show its name/slug in the trail.
  const primaryTask = useMemo(() => {
    const tasks = datasetTasksQ.data || [];
    if (!currentTaskId) return tasks[0] || null;
    return tasks.find((t) => t.id === currentTaskId) || tasks[0] || null;
  }, [datasetTasksQ.data, currentTaskId]);

  const areaQ = useQuery({
    queryKey: ["area", primaryTask?.area_id],
    queryFn: () => catalogApi.getArea(primaryTask!.area_id!),
    enabled: !!primaryTask?.area_id,
    staleTime: 10 * 60 * 1000,
  });

  if (datasetQ.isLoading) {
    return (
      <div className="page">
        <Skeleton className="h-12 w-1/2 mb-6" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (datasetQ.error || !datasetQ.data) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Benchmark not found.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const dataset = datasetQ.data;
  // Sort by the *active* metric, not the stored `best_rank`. `best_rank` is
  // computed per (task, dataset, best_metric) on the backend, so it only
  // matches the leaderboard when the row's primary metric == the displayed
  // metric. When the user clicks an alternate metric tab (Recall on an
  // F1-primary benchmark, for example), we re-rank in-client by the actual
  // value. Rows that don't carry the active metric drop to the end, ordered
  // by their stored rank as a deterministic tie-breaker.
  const tableRows = displayedLeaderboardEvals;
  const sortedRows = tableRows.slice().sort((a, b) => {
    const va = parseMetricValue(a.metrics?.[activeMetric]);
    const vb = parseMetricValue(b.metrics?.[activeMetric]);
    if (va !== null && vb !== null) {
      return arrow === "↓" ? va - vb : vb - va;
    }
    if (va !== null) return -1;
    if (vb !== null) return 1;
    return storedRankForMetric(a, activeMetric) - storedRankForMetric(b, activeMetric);
  });
  const showHarness = Boolean(dataset.supports_harness);
  const parameterCoverage = {
    parameter_coverage_known: mergedTaskEvals.filter((entry) => entry.parameterCount !== null).length,
    parameter_coverage_total: mergedTaskEvals.length,
  };
  const hasParameterMetadata = parameterCoverage.parameter_coverage_known > 0;
  const parameterFilterHasMatches = (bound: number | undefined) =>
    filterLeaderboardByParameterCount(mergedTaskEvals, bound).length > 0;
  const setParameterFilter = (bound: number | undefined) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (bound === undefined) next.delete("max_parameters_exclusive");
      else next.set("max_parameters_exclusive", String(bound));
      return next;
    });
  };
  const setMetric = (metric: string) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("metric", metric);
      return next;
    });
  };
  const highlightedEval = highlightEvalId
    ? sortedRows.find((e) => evaluationMatchesHighlight(e, highlightEvalId)) || null
    : null;

  const introducingPaper = dataset.introducing_paper ?? undefined;
  const sourcePaperRouteId =
    introducingPaper?.arxiv_id ||
    introducingPaper?.id ||
    extractSourcePaperRouteId(dataset.paper_url);
  const sourcePaperTitle =
    introducingPaper?.title || dataset.introducing_paper_title || null;
  const sourcePaperYear = introducingPaper?.published?.slice(0, 4) || dataset.introduced_year || null;
  const hasSource = !!sourcePaperRouteId || !!dataset.paper_url || !!sourcePaperTitle;
  const sourcePaperFallbackLabel =
    introducingPaper?.arxiv_id || dataset.paper_url?.match(/^https?:\/\/(?:www\.)?arxiv\.org\//i)
      ? `arXiv:${sourcePaperRouteId}`
      : `Paper ${sourcePaperRouteId}`;

  return (
    <div className="page">
      <div className="bm-page">
        <div className="breadcrumb">
          <Link to="/tasks">Tasks</Link>
          {areaQ.data && (
            <>
              <span className="sep">/</span>
              <Link to={`/tasks#area-${slugify(areaQ.data.name)}`}>
                {areaQ.data.name}
              </Link>
            </>
          )}
          {primaryTask && (
            <>
              <span className="sep">/</span>
              <Link to={`/tasks/${primaryTask.slug || primaryTask.id}`}>
                {primaryTask.name}
              </Link>
            </>
          )}
          <span className="sep">/</span>
          <span style={{ color: "var(--accent-text)" }}>{dataset.name}</span>
        </div>

        <div className="bm-title-row">
          <h1 className="bm-title">{dataset.name}</h1>
          {benchmarkTrend && (
            <div className="bm-title-trend" aria-label={`${dataset.name} reporting trend`}>
              <BenchmarkTrendSparkline
                history={benchmarkTrend.history}
                benchmarkName={benchmarkTrend.name}
              />
              <span className="bm-title-trend-summary">
                <strong>{benchmarkTrend.recent_paper_count}</strong>{" "}
                {benchmarkTrend.recent_paper_count === 1 ? "paper" : "papers"}
                {benchmarkTrend.rate_change == null ? (
                  benchmarkTrend.recent_paper_count > 0 && (
                    <span className="benchmark-trend-change is-new">new</span>
                  )
                ) : (
                  <span
                    className={`benchmark-trend-change ${
                      benchmarkTrend.rate_change >= 1 ? "is-up" : "is-down"
                    }`}
                  >
                    {benchmarkTrend.rate_change >= 1 ? "↑" : "↓"}{" "}
                    {benchmarkTrend.rate_change.toFixed(1)}×
                  </span>
                )}
              </span>
            </div>
          )}
        </div>

        <div className="bm-subtitle">
          {isSummaryLoading ? (
            <Skeleton
              className="h-5 w-64 bm-summary-skeleton"
              aria-label="Loading benchmark summary"
            />
          ) : (
            <span>
              {displayedMetric && (
                <>
                  <span className="metric-tag">{displayedMetric}</span>
                  <span style={{ color: "var(--hairline-strong)", margin: "0 8px" }}>·</span>
                </>
              )}
              {displayedSotaModel ? (
                <span>
                  Best: <span className="best-name">{formatMetricValue(displayedSota)}</span> by <span className="best-name" style={{ fontStyle: "normal" }}>{displayedSotaModel}</span>
                </span>
              ) : (
                <span>{sortedRows.length} evaluations</span>
              )}
            </span>
          )}
          {dataset.hf_url && (
            <a
              className="bm-action-btn"
              href={dataset.hf_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              <span aria-hidden="true">🤗</span> View on Hugging Face
            </a>
          )}
        </div>

        {dataset.description && (
          <p className="bm-description">{dataset.description}</p>
        )}

        {preferences.hide_closed_source_evals && hiddenClosedEvals.length > 0 && (
          <div className="bm-hidden-closed-notice">
            <span>
              {hiddenClosedEvals.length} closed-source {hiddenClosedEvals.length === 1 ? "row is" : "rows are"} hidden
              {hiddenClosedTopEval?.model_name ? (
                <>
                  , including <strong>{hiddenClosedTopEval.model_name}</strong>
                </>
              ) : null}
              .
            </span>
            <button
              type="button"
              className="bm-hidden-closed-action"
              onClick={() => {
                void setHideClosedSourceEvals(false);
              }}
            >
              Show closed-source
            </button>
          </div>
        )}

        {hasSource && (
          <div className="method-source" style={{ marginTop: 0, marginBottom: 18 }}>
            <span className="method-source-label">Source</span>
            {sourcePaperRouteId ? (
              <Link
                to={`/paper/${sourcePaperRouteId}`}
                target="_blank"
                rel="noopener noreferrer"
                className="method-source-link"
              >
                <span className="method-source-title">
                  {sourcePaperTitle ? (
                    <LatexTitle title={sourcePaperTitle} />
                  ) : (
                    sourcePaperFallbackLabel
                  )}
                </span>
                {sourcePaperYear && (
                  <span className="method-source-meta">{sourcePaperYear}</span>
                )}
              </Link>
            ) : dataset.paper_url ? (
              <a
                href={safeExternalHref(dataset.paper_url) ?? undefined}
                target="_blank"
                rel="noopener noreferrer"
                className="method-source-link"
              >
                <span className="method-source-title">
                  {sourcePaperTitle ? (
                    <LatexTitle title={sourcePaperTitle} />
                  ) : (
                    dataset.paper_url
                  )}
                </span>
                {sourcePaperYear && (
                  <span className="method-source-meta">{sourcePaperYear}</span>
                )}
              </a>
            ) : (
              <div className="method-source-link is-static">
                <span className="method-source-title">
                  {sourcePaperTitle ? <LatexTitle title={sourcePaperTitle} /> : null}
                </span>
                {sourcePaperYear && (
                  <span className="method-source-meta">{sourcePaperYear}</span>
                )}
              </div>
            )}
          </div>
        )}

        {!isInitialFilteredViewLoading && chartPoints.length > 0 && (
          <div className="bm-card" ref={chartCardRef}>
            <div className="bm-card-screenshot-header" aria-hidden="true">
              <div className="bm-card-screenshot-title">
                <span className="bm-card-screenshot-eyebrow">Benchmark</span>
                <span className="bm-card-screenshot-name">{dataset.name}</span>
              </div>
              <div className="bm-card-screenshot-brand">
                <span className="brand">
                  <span className="brand-mark"></span>
                  <span className="brand-name">Papers <em>With Code</em></span>
                </span>
                <span className="bm-card-screenshot-url">paperswithcode.co</span>
              </div>
            </div>
            <div className="bm-card-head">
              <div className="bm-card-title">SOTA progression</div>
              <div className="bm-card-actions">
                {allowedMetrics.length > 1 && (
                  <label className="bm-view-select">
                    <span className="bm-view-select-label">View</span>
                    <select
                      value={activeMetric}
                      onChange={(e) => setMetric(e.target.value)}
                    >
                      {orderedMetrics.map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </label>
                )}
                <label className="bm-closed-toggle" title="Show or hide evaluations of closed-source models">
                  <Switch
                    className="bm-closed-toggle-switch"
                    checked={!preferences.hide_closed_source_evals}
                    onCheckedChange={(checked) => {
                      void setHideClosedSourceEvals(!checked);
                    }}
                    aria-label="Show closed-source models"
                  />
                  <span className="bm-closed-toggle-label">Closed-source</span>
                </label>
                <CopyScreenshotButton targetRef={chartCardRef} label="SOTA chart" />
              </div>
            </div>
            <div className="bm-chart-wrap">
              <BenchmarkChart points={chartPoints} metric={activeMetric} />
            </div>
            <div className="bm-chart-foot">
              <span className="legend-dot"></span>
              {parameterBound === undefined ? "All models" : "Filtered models"} over time · highlighted dots track the running best · hover for the model · click to open the paper
            </div>
          </div>
        )}

        {highlightedEval && (() => {
          const paperRouteId = highlightedEval.paper_arxiv_id || highlightedEval.paper_id;
          const paperLabel =
            highlightedEval.paper_title ||
            (highlightedEval.paper_arxiv_id
              ? `arXiv:${highlightedEval.paper_arxiv_id}`
              : null);
          const metricForRow =
            highlightedEval.best_metric && highlightedEval.metrics?.[highlightedEval.best_metric] !== undefined
              ? highlightedEval.best_metric
              : activeMetric;
          const metricValue = highlightedEval.metrics?.[metricForRow];
          return (
            <div className="bm-highlight-banner" role="status">
              <span className="bm-highlight-dot" aria-hidden="true" />
              <div className="bm-highlight-text">
                <span className="bm-highlight-label">Comparing result</span>
                <span className="bm-highlight-paper">
                  {highlightedEval.model_name || paperLabel || "—"}
                  {highlightedEval.harness ? ` · ${highlightedEval.harness}` : ""}
                </span>
                <span className="bm-highlight-meta">
                  {metricValue !== undefined && metricForRow ? (
                    <>
                      {metricForRow}: {formatMetricValue(metricValue)}
                      {paperLabel ? " · " : ""}
                    </>
                  ) : null}
                  {paperRouteId ? (
                    <Link to={`/paper/${paperRouteId}`}>
                      {renderBenchmarkPaperTitle(highlightedEval.paper_title, paperLabel)}
                    </Link>
                  ) : (
                    renderBenchmarkPaperTitle(highlightedEval.paper_title, paperLabel)
                  )}
                </span>
              </div>
            </div>
          );
        })()}

        <div className="bm-card" ref={leaderboardCardRef}>
          <div className="bm-card-screenshot-header" aria-hidden="true">
            <div className="bm-card-screenshot-title">
              <span className="bm-card-screenshot-eyebrow">Benchmark</span>
              <span className="bm-card-screenshot-name">{dataset.name}</span>
            </div>
            <div className="bm-card-screenshot-brand">
              <span className="brand">
                <span className="brand-mark"></span>
                <span className="brand-name">Papers <em>With Code</em></span>
              </span>
              <span className="bm-card-screenshot-url">paperswithcode.co</span>
            </div>
          </div>
          <div className="bm-card-head">
            <div className="bm-card-title">Leaderboard</div>
            <div className="bm-card-actions">
              {allowedMetrics.length > 1 && (
                <label className="bm-view-select">
                  <span className="bm-view-select-label">View</span>
                  <select
                    value={activeMetric}
                    onChange={(e) => setMetric(e.target.value)}
                  >
                    {orderedMetrics.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </label>
              )}
              <label className="bm-closed-toggle" title="Show or hide evaluations of closed-source models">
                <Switch
                  className="bm-closed-toggle-switch"
                  checked={!preferences.hide_closed_source_evals}
                  onCheckedChange={(checked) => {
                    void setHideClosedSourceEvals(!checked);
                  }}
                  aria-label="Show closed-source models"
                />
                <span className="bm-closed-toggle-label">Closed-source</span>
              </label>
              {!isInitialFilteredViewLoading && !hasParameterMetadata && evalsQ.isSuccess ? (
                <span className="bm-parameter-unavailable">Parameter metadata unavailable</span>
              ) : null}
              <CopyScreenshotButton targetRef={leaderboardCardRef} label="leaderboard" />
            </div>
          </div>
          {!isInitialFilteredViewLoading && hasParameterMetadata && (
            <div className="bm-parameter-filter-bar">
              <span className="bm-parameter-filter-label">Parameters Size</span>
              <div className="bm-parameter-filter-options" role="group" aria-label="Filter leaderboard by parameter size">
                {PARAMETER_FILTERS.map((filter) => {
                  const selected = parameterBound === filter.maxParametersExclusive;
                  const disabled = !selected && !parameterFilterHasMatches(filter.maxParametersExclusive);
                  return (
                    <button
                      key={filter.label}
                      type="button"
                      className={`bm-parameter-filter-option${selected ? " is-active" : ""}`}
                      aria-pressed={selected}
                      disabled={disabled}
                      onClick={() => setParameterFilter(filter.maxParametersExclusive)}
                    >
                      {filter.label}
                    </button>
                  );
                })}
              </div>
              <span className="bm-parameter-coverage">
                Parameters known for {parameterCoverage.parameter_coverage_known} of {parameterCoverage.parameter_coverage_total} entries
              </span>
            </div>
          )}
          {evalsQ.isLoading || isInitialFilteredViewLoading ? (
            <div style={{ padding: 16 }}>
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full mb-2" />
              ))}
            </div>
          ) : sortedRows.length === 0 ? (
            parameterBound ? (
              <div className="no-results">
                No known parameter counts match this filter. {" "}
                <button type="button" className="bm-empty-filter-action" onClick={() => setParameterFilter(undefined)}>Show all</button>
              </div>
            ) : <div className="no-results">No evaluations submitted yet.</div>
          ) : (
            <>
            {orderedMetrics.length > 1 && (
              <div className="bm-metric-columns-control">
                <button
                  type="button"
                  className="bm-metric-columns-toggle"
                  aria-expanded={showMoreMetrics}
                  aria-controls="benchmark-leaderboard"
                  onClick={() => setExpandedMetricScope(showMoreMetrics ? null : metricScope)}
                >
                  {showMoreMetrics ? "Show selected metric only" : `Show more metrics (${orderedMetrics.length - 1})`}
                </button>
                {showMoreMetrics && <span>Scroll metrics horizontally; model and paper details stay visible.</span>}
              </div>
            )}
            <div ref={setTableScrollElement} className="bm-table-scroll" role="region" aria-label="Leaderboard metrics" tabIndex={0}>
            <table
              id="benchmark-leaderboard"
              className="bm-table"
              style={{ "--bm-metric-count": visibleMetrics.length, "--bm-harness-count": showHarness ? 1 : 0 } as React.CSSProperties}
            >
              <colgroup>
                <col className="bm-width-rank" />
                <col className="bm-width-model" />
                <col className="bm-width-parameters" />
                {showHarness && <col className="bm-width-harness" />}
                {visibleMetrics.map((m) => <col key={m} className="bm-width-metric" />)}
                <col />
                <col className="bm-width-year" />
              </colgroup>
              <thead>
                <tr>
                  <th className="col-rank">Rank</th>
                  <th className="col-model">Model</th>
                  <th className="col-parameters">Parameters</th>
                  {showHarness && <th className="col-harness">Harness</th>}
                  {visibleMetrics.map((m) => {
                    const isActive = m === activeMetric;
                    return (
                      <th
                        key={m}
                        className={`col-value ${isActive ? "is-active" : ""}`}
                        aria-sort={isActive ? (arrow === "↓" ? "ascending" : "descending") : "none"}
                      >
                        <button
                          type="button"
                          className="bm-metric-header"
                          onClick={() => setMetric(m)}
                          aria-pressed={isActive}
                          title={`Sort by ${m}`}
                        >
                          {m}{isActive ? ` ${arrow}` : ""}
                        </button>
                      </th>
                    );
                  })}
                  <th className="col-paper">Paper</th>
                  <th className="col-year">Year</th>
                </tr>
              </thead>
              <tbody>
                {(() => {
                  // Re-derive ranks from the active-metric ordering with ties
                  // getting equal ranks (so two models that share a Recall of
                  // 0.98 both show as #1). Rows without a numeric value for
                  // the active metric are unranked.
                  let lastValue: number | null = null;
                  let lastRank = 0;
                  return sortedRows.map((e, i) => {
                    const value = parseMetricValue(e.metrics?.[activeMetric]);
                    let rank: number | null = null;
                    if (value !== null) {
                      if (lastValue === null || value !== lastValue) {
                        lastRank = i + 1;
                        lastValue = value;
                      }
                      rank = lastRank;
                    }
                    const paperRouteId = e.paper_arxiv_id || e.paper_id;
                    const paperLabel =
                      e.paper_title || (e.paper_arxiv_id ? `arXiv:${e.paper_arxiv_id}` : null);
                    const isHighlighted = evaluationMatchesHighlight(e, highlightEvalId);
                    return (
                      <tr
                        key={e.id}
                        ref={isHighlighted ? highlightRowRef : undefined}
                        className={isHighlighted ? "is-highlighted" : undefined}
                      >
                        <td className="col-rank">{rank ?? "—"}</td>
                        <td className="col-model">
                          {isHighlighted && <span className="bm-row-marker" aria-hidden="true" />}
                          {e.hf_model_url ? (
                            <a
                              href={e.hf_model_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="bm-model-link"
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
                        <td
                          className="col-parameters"
                          title={e.parameterCount === null ? undefined : e.parameterCount.toLocaleString("en-US")}
                          aria-label={e.parameterCount === null ? "Parameters unknown" : `${e.parameterCount.toLocaleString("en-US")} parameters`}
                        >
                          {e.parameterCount === null ? "—" : formatParameterCount(e.parameterCount)}
                        </td>
                        {showHarness && (
                          <td className="col-harness">{e.harness || "—"}</td>
                        )}
                        {visibleMetrics.map((m) => {
                          const isActive = m === activeMetric;
                          const raw = e.metrics?.[m];
                          return (
                            <td
                              key={m}
                              className={`col-value${isActive ? " is-active" : ""}${isActive && rank === 1 ? " is-best" : ""}`}
                            >
                              {raw !== undefined && raw !== null && raw !== ""
                                ? formatMetricValue(raw)
                                : "—"}
                            </td>
                          );
                        })}
                        <td className="col-paper">
                          {paperRouteId ? (
                            <Link to={`/paper/${paperRouteId}`} title={e.paper_title || paperLabel || undefined}>
                              {renderBenchmarkPaperTitle(e.paper_title, paperLabel)}
                            </Link>
                          ) : (
                            renderBenchmarkPaperTitle(e.paper_title, paperLabel)
                          )}
                        </td>
                        <td className="col-year">{(e.evaluated_on || e.paper_published_date)?.slice(0, 4) || "—"}</td>
                      </tr>
                    );
                  });
                })()}
              </tbody>
            </table>
            </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default BenchmarkDetailView;

import ResearchFollowButton from "@/components/ResearchFollowButton";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import type { Task } from "@/lib/api/catalog.types";
import type { LeaderboardMetric, MetricDirections } from "@/lib/api/evaluations.types";
import { catalogApi } from "@/lib/api/catalog";
import { evaluationsApi } from "@/lib/api/evaluations";
import { usePreferences } from "@/lib/preferences";
import { formatMetricValue } from "@/lib/utils";
import { deriveLeaderboardPresentation, resolveLeaderboardTask } from "@/lib/leaderboardPresentation";
import BenchmarkTable from "@/components/benchmark/BenchmarkTable";
import BenchmarkProgression from "@/components/benchmark/BenchmarkProgression";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Alert, AlertDescription } from "@/components/ui/alert";
import LatexTitle from "@/components/LatexTitle";
import BenchmarkTrendSparkline from "@/components/BenchmarkTrendSparkline";
import CopyScreenshotButton from "@/components/benchmark/CopyScreenshotButton";
import { parseParameterFilter } from "@/lib/benchmarkLeaderboard";
import "@/styles/benchmark-detail.css";
import { safeExternalHref } from "@/lib/safeExternalHref";
import { slugify } from "@/lib/slug";
import { isNotFound } from "@/lib/apiErrors";
import NotFound from "@/pages/NotFound";
import { catalogQueryKeys, evaluationQueryKeys, TEN_MINUTES } from "@/lib/api/queryKeys";

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
  const leaderboardCardRef = useRef<HTMLDivElement | null>(null);
  const [expandedMetricScope, setExpandedMetricScope] = useState<string | null>(null);
  const metricScope = `${datasetSlug}:${taskSlugFromQuery || ""}`;
  const showMoreMetrics = expandedMetricScope === metricScope;
  const [fittingMetricCount, setFittingMetricCount] = useState(1);

  // Fetching the dataset with `include_paper=true` collapses the previous
  // dataset → paper waterfall into a single round trip.
  const datasetQ = useQuery({
    queryKey: [
      ...catalogQueryKeys.dataset(datasetSlug),
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
    staleTime: TEN_MINUTES,
  });

  // Fetch every evaluation on this dataset once. Metric switching is purely
  // a UI concern (column choice, sort key, SOTA computation), so we must not
  // pass the selected metric as an API filter — the backend filters on the row's
  // `best_metric` column, which would drop rows whose primary metric is
  // different from the tab the user clicked (e.g. an F1-primary row that
  // also carries Recall/Precision values).
  const evalsQ = useQuery({
    queryKey: evaluationQueryKeys.byDataset(datasetQ.data?.id),
    queryFn: () => evaluationsApi.byDataset(datasetQ.data!.id),
    enabled: !!datasetQ.data?.id,
    staleTime: 5 * 60 * 1000,
  });

  const datasetTasksQ = useQuery<Task[]>({
    queryKey: [...catalogQueryKeys.datasetTasks, datasetQ.data?.id],
    queryFn: () => catalogApi.datasetTasks(datasetQ.data!.id),
    enabled: !!datasetQ.data?.id,
    staleTime: TEN_MINUTES,
  });

  const directionsQ = useQuery<MetricDirections>({
    queryKey: ["metric-directions"],
    queryFn: () => catalogApi.metricDirections(),
    staleTime: 60 * 60 * 1000,
  });

  const currentTaskId = resolveLeaderboardTask(
    datasetTasksQ.data || [],
    evalsQ.data || [],
    taskSlugFromQuery,
    highlightEvalId,
  );

  const benchmarkTrendsQ = useQuery({
    queryKey: [
      ...catalogQueryKeys.taskBenchmarkTrends,
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
    staleTime: TEN_MINUTES,
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
    staleTime: TEN_MINUTES,
  });

  const model = deriveLeaderboardPresentation({
    evaluations: evalsQ.data || [],
    tasks: datasetTasksQ.data || [],
    configuredMetrics: leaderboardMetricsQ.data || [],
    directions: directionsQ.data,
    initialSummary: datasetQ.data?.leaderboard_summary,

    taskSlug: taskSlugFromQuery,
    highlightEvalId,
    metric: searchParams.get("metric") || undefined,
    hideClosed: preferences.hide_closed_source_evals,
    parameterBound,
    showMoreMetrics,
    fittingMetricCount,
    ready: {
      evaluations: evalsQ.isSuccess,
      tasks: datasetTasksQ.isSuccess,
      directions: directionsQ.isSuccess,
      metrics: leaderboardMetricsQ.isSuccess,
    },
  });
  const {
    primaryTask, hiddenClosedEvals, hiddenClosedTopEval,
    isSummaryLoading, displayedMetric, displayedSota, displayedSotaModel,
    isInitialFilteredViewLoading, highlightedEval,
    hasParameterMetadata, parameterCoverage, orderedMetrics,
  } = model;

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

  const areaQ = useQuery({
    queryKey: catalogQueryKeys.area(primaryTask?.area_id),
    queryFn: () => catalogApi.getArea(primaryTask!.area_id!),
    enabled: !!primaryTask?.area_id,
    staleTime: TEN_MINUTES,
  });

  if (datasetQ.isLoading) {
    return (
      <div className="page">
        <Skeleton className="h-12 w-1/2 mb-6" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isNotFound(datasetQ.error)) return <NotFound />;
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
  const showHarness = Boolean(dataset.supports_harness);
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

        <ResearchFollowButton kind="benchmark" entityId={dataset.id} />

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
                <span>{model.rows.length} evaluations</span>
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
                setHideClosedSourceEvals(false);
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

        <BenchmarkProgression model={model} datasetName={dataset.name} hideClosed={preferences.hide_closed_source_evals}
          setHideClosed={setHideClosedSourceEvals} setMetric={setMetric} />

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
              : model.activeMetric;
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
              {model.allowedMetrics.length > 1 && (
                <label className="bm-view-select">
                  <span className="bm-view-select-label">View</span>
                  <select
                    value={model.activeMetric}
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
                    setHideClosedSourceEvals(!checked);
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
                {model.parameterFilters.map((filter) => {
                  const { selected, disabled } = filter;
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
          ) : model.rows.length === 0 ? (
            parameterBound ? (
              <div className="no-results">
                No known parameter counts match this filter. {" "}
                <button type="button" className="bm-empty-filter-action" onClick={() => setParameterFilter(undefined)}>Show all</button>
              </div>
            ) : <div className="no-results">No evaluations submitted yet.</div>
          ) : (
            <>
            {orderedMetrics.length > fittingMetricCount && (
              <div className="bm-metric-columns-control">
                <button
                  type="button"
                  className="bm-metric-columns-toggle"
                  aria-expanded={showMoreMetrics}
                  aria-controls="benchmark-leaderboard"
                  onClick={() => setExpandedMetricScope(showMoreMetrics ? null : metricScope)}
                >
                  {showMoreMetrics ? "Show fewer metrics" : `Show more metrics (${orderedMetrics.length - fittingMetricCount})`}
                </button>
                {showMoreMetrics && <span>Scroll metrics horizontally; model and paper details stay visible.</span>}
              </div>
            )}
            <BenchmarkTable model={model} showHarness={showHarness} setMetric={setMetric} highlightRowRef={highlightRowRef} onFittingMetricCountChange={setFittingMetricCount} />
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default BenchmarkDetailView;

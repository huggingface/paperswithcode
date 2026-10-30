import type { Dataset, Task } from "@/lib/api/catalog.types";
import type {
  Evaluation,
  LeaderboardMetric,
  MetricDirections,
} from "@/lib/api/evaluations.types";
import {
  computeSeries,
  evaluationMatchesHighlight,
  filterLeaderboardByParameterCount,
  mergeLeaderboardEvaluations,
  parseMetricValue,
  storedRankForMetric,
  PARAMETER_FILTERS,
} from "@/lib/benchmarkLeaderboard";

interface LeaderboardEvaluationVisibility {
  visible: Evaluation[];
  hiddenClosed: Evaluation[];
  topHiddenClosed: Evaluation | null;
}

function selectLeaderboardEvaluations(
  evaluations: Evaluation[] | undefined,
  taskId: string | null | undefined,
  hideClosedSource: boolean,
): LeaderboardEvaluationVisibility {
  const current = taskId
    ? (evaluations ?? []).filter((evaluation) => evaluation.task_id === taskId)
    : evaluations ?? [];
  const hiddenClosed = current.filter((evaluation) => evaluation.is_open === false);
  const topHiddenClosed = hiddenClosed.reduce<Evaluation | null>((best, evaluation) => {
    if (!best) return evaluation;
    return (evaluation.best_rank ?? Number.POSITIVE_INFINITY) <
      (best.best_rank ?? Number.POSITIVE_INFINITY)
      ? evaluation
      : best;
  }, null);

  return {
    visible: hideClosedSource
      ? current.filter((evaluation) => evaluation.is_open !== false)
      : current,
    hiddenClosed,
    topHiddenClosed,
  };
}

/** Resolve query dependencies with the same precedence used by the presentation. */
export function resolveLeaderboardTask(
  tasks: Task[],
  evaluations: Evaluation[],
  taskSlug?: string,
  highlightEvalId?: string,
): string | null {
  const highlightEval = evaluations.find((e) => e.id === highlightEvalId);
  if (tasks.length === 0) return null;
  if (
    highlightEval?.task_id &&
    tasks.some((t) => t.id === highlightEval.task_id)
  ) {
    return highlightEval.task_id;
  }
  if (taskSlug) {
    const match = tasks.find((t) => t.slug === taskSlug);
    if (match) return match.id;
  }
  if (tasks.length === 1) return tasks[0].id;
  if (evaluations.length > 0) {
    const counts = new Map<string, number>();
    for (const e of evaluations) {
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
}

export interface LeaderboardPresentationInput {
  evaluations: Evaluation[];
  tasks: Task[];
  taskSlug?: string;
  highlightEvalId?: string;
  metric?: string;
  configuredMetrics: LeaderboardMetric[];
  directions?: MetricDirections;
  hideClosed: boolean;
  parameterBound?: number;
  showMoreMetrics: boolean;
  /** Metric columns that fit beside the fixed columns; at least one is shown. */
  fittingMetricCount?: number;
  initialSummary?: Dataset["leaderboard_summary"];
  ready: {
    evaluations: boolean;
    tasks: boolean;
    directions: boolean;
    metrics: boolean;
  };
}

// backend/services/leaderboard_ranking_service.py mirrors the default ranking
// for crawlable benchmark HTML; keep the two in step.
export function deriveLeaderboardPresentation(
  input: LeaderboardPresentationInput,
) {
  const {
    evaluations,
    tasks,
    taskSlug,
    highlightEvalId,
    parameterBound,
    showMoreMetrics,
    fittingMetricCount = 1,
  } = input;
  const currentTaskId = resolveLeaderboardTask(
    tasks,
    evaluations,
    taskSlug,
    highlightEvalId,
  );
  const primaryTask =
    tasks.find((task) => task.id === currentTaskId) || tasks[0] || null;
  const highlightEval = evaluations.find((e) => e.id === highlightEvalId);
  const visibility = selectLeaderboardEvaluations(
    evaluations,
    currentTaskId,
    input.hideClosed,
  );
  const mergedTaskEvals = mergeLeaderboardEvaluations(visibility.visible);
  const displayedLeaderboardEvals = filterLeaderboardByParameterCount(
    mergedTaskEvals,
    parameterBound,
  );
  const configuredMetrics = input.configuredMetrics.map(
    (metric) => metric.metric_name,
  );
  const dataMetrics = Array.from(
    new Set(
      mergedTaskEvals.flatMap((e) => [
        ...(e.best_metric ? [e.best_metric] : []),
        ...Object.keys(e.metrics || {}),
      ]),
    ),
  );
  const allowedMetrics = configuredMetrics.length
    ? configuredMetrics
    : dataMetrics;
  const counts = new Map<string, number>();
  for (const entry of mergedTaskEvals) {
    const metric = entry.best_metric;
    if (!metric || parseMetricValue(entry.metrics[metric]) === null) continue;
    if (configuredMetrics.length && !allowedMetrics.includes(metric)) continue;
    counts.set(metric, (counts.get(metric) || 0) + 1);
  }
  const defaultMetric =
    [...counts].sort((a, b) => b[1] - a[1])[0]?.[0] || allowedMetrics[0] || "";
  const requestedMetric = allowedMetrics.find(
    (metric) =>
      metric.toLocaleLowerCase() === input.metric?.trim().toLocaleLowerCase(),
  );
  const activeMetric =
    requestedMetric || highlightEval?.best_metric || defaultMetric;
  const arrow: "↑" | "↓" =
    input.directions?.directions[activeMetric] === "lower_is_better"
      ? "↓"
      : "↑";
  const orderedMetrics =
    activeMetric && allowedMetrics.includes(activeMetric)
      ? [
          activeMetric,
          ...allowedMetrics.filter((metric) => metric !== activeMetric),
        ]
      : allowedMetrics;
  const visibleMetrics = orderedMetrics.length
    ? showMoreMetrics
      ? orderedMetrics
      : orderedMetrics.slice(0, Math.max(1, fittingMetricCount))
    : activeMetric
      ? [activeMetric]
      : [];
  const sortedRows = displayedLeaderboardEvals.slice().sort((a, b) => {
    const va = parseMetricValue(a.metrics[activeMetric]);
    const vb = parseMetricValue(b.metrics[activeMetric]);
    if (va !== null && vb !== null) return arrow === "↓" ? va - vb : vb - va;
    if (va !== null) return -1;
    if (vb !== null) return 1;
    return (
      storedRankForMetric(a, activeMetric) -
      storedRankForMetric(b, activeMetric)
    );
  });
  let lastValue: number | null = null;
  let lastRank = 0;
  const rows = sortedRows.map((evaluation, index) => {
    const value = parseMetricValue(evaluation.metrics[activeMetric]);
    if (value !== null && value !== lastValue) {
      lastValue = value;
      lastRank = index + 1;
    }
    return {
      evaluation,
      rank: value === null ? null : lastRank,
      isHighlighted: evaluationMatchesHighlight(evaluation, highlightEvalId),
    };
  });
  const {
    points: chartPoints,
    sota,
    sotaModel,
  } = computeSeries(displayedLeaderboardEvals, activeMetric, arrow);
  const initialSummary =
    parameterBound === undefined ? input.initialSummary : undefined;
  const isFullSummaryReady =
    input.ready.evaluations &&
    input.ready.tasks &&
    input.ready.directions &&
    (!currentTaskId || input.ready.metrics);
  const parameterCoverage = {
    parameter_coverage_known: mergedTaskEvals.filter(
      (entry) => entry.parameterCount !== null,
    ).length,
    parameter_coverage_total: mergedTaskEvals.length,
  };
  return {
    currentTaskId,
    primaryTask,

    activeMetric,
    arrow,
    allowedMetrics,
    orderedMetrics,
    visibleMetrics,

    rows,
    chartPoints,
    highlightedEval: rows.find((row) => row.isHighlighted)?.evaluation || null,
    hiddenClosedEvals: visibility.hiddenClosed,
    hiddenClosedTopEval: visibility.topHiddenClosed,

    parameterBound,
    parameterCoverage,
    hasParameterMetadata: parameterCoverage.parameter_coverage_known > 0,
    parameterFilters: PARAMETER_FILTERS.map((filter) => ({
      ...filter,
      selected: parameterBound === filter.maxParametersExclusive,
      disabled:
        parameterBound !== filter.maxParametersExclusive &&
        filterLeaderboardByParameterCount(
          mergedTaskEvals,
          filter.maxParametersExclusive,
        ).length === 0,
    })),

    displayedMetric: isFullSummaryReady ? activeMetric : initialSummary?.metric,
    displayedSota: isFullSummaryReady ? sota : initialSummary?.value,
    displayedSotaModel: isFullSummaryReady
      ? sotaModel
      : initialSummary?.model_name,
    isSummaryLoading: !isFullSummaryReady && !initialSummary,
    isInitialFilteredViewLoading:
      parameterBound !== undefined && !isFullSummaryReady,
  };
}

export type LeaderboardPresentation = ReturnType<
  typeof deriveLeaderboardPresentation
>;

export interface LeaderboardColumnWidths {
  fixed: number;
  harness: number;
  metric: number;
}

/**
 * How many metric columns fit in `availableWidth` beside the fixed columns,
 * given the `current` count. Shrinks as soon as a column no longer fits, but
 * grows only with `growSlack` spare pixels: showing another column can wrap
 * paper titles and add a page scrollbar, which would narrow the table again
 * and flip the count back and forth at a column boundary.
 */
export function countFittingMetricColumns(
  availableWidth: number,
  widths: LeaderboardColumnWidths,
  showHarness: boolean,
  current = 1,
  growSlack = 0,
): number {
  const remaining =
    availableWidth - widths.fixed - (showHarness ? widths.harness : 0);
  if (widths.metric <= 0) return 1;
  const fitting = Math.floor(remaining / widths.metric);
  if (fitting < current) return Math.max(1, fitting);
  const grown = Math.floor(
    (remaining - growSlack) / widths.metric,
  );
  return Math.max(1, current, grown);
}

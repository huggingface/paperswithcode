import type { Evaluation } from "@/lib/api/evaluations.types";

export interface ChartPoint {
  value: number;
  date: string;
  dateLabel: string;
  modelName: string;
  paperTitle: string;
  paperRouteId: string | null;
  isSota: boolean;
}

/**
 * Parse a stored metric value into a number. Handles "88.55 ± 0.04" style
 * strings (we keep the central estimate and drop the uncertainty), plain
 * numeric strings, and already-numeric values. Returns null when the value
 * isn't usable for comparisons so callers can push those rows to the end.
 */
export function parseMetricValue(raw: string | number | undefined | null): number | null {
  if (raw == null) return null;
  if (typeof raw === "number") return Number.isFinite(raw) ? raw : null;
  const s = raw.includes("±") ? raw.split("±")[0].trim() : raw.trim();
  const n = parseFloat(s);
  return Number.isFinite(n) ? n : null;
}

export type MergedEvaluation = Evaluation & {
  /** Source evaluation ids folded into this display row. */
  sourceEvaluationIds: string[];
  /** Per-metric stored ranks from the underlying evaluation rows. */
  ranksByMetric: Record<string, number>;
  /** A parameter count is displayable only when sibling metric rows agree. */
  parameterCount: number | null;
  hasParameterConflict: boolean;
};

export const PARAMETER_FILTERS = [
  { label: "All", maxParametersExclusive: undefined },
  { label: "<1B", maxParametersExclusive: 1_000_000_000 },
  { label: "<3B", maxParametersExclusive: 3_000_000_000 },
  { label: "<6B", maxParametersExclusive: 6_000_000_000 },
  { label: "<12B", maxParametersExclusive: 12_000_000_000 },
  { label: "<32B", maxParametersExclusive: 32_000_000_000 },
  { label: "<128B", maxParametersExclusive: 128_000_000_000 },
  { label: "<500B", maxParametersExclusive: 500_000_000_000 },
] as const;

export function parseParameterFilter(value: string | null): number | undefined {
  const parsed = value === null ? undefined : Number(value);
  return PARAMETER_FILTERS.some((filter) => filter.maxParametersExclusive === parsed)
    ? parsed
    : undefined;
}

export function formatParameterCount(count: number): string {
  return new Intl.NumberFormat("en", {
    notation: "compact",
    maximumSignificantDigits: 3,
  }).format(count);
}

function leaderboardRowKey(e: Evaluation): string {
  return [
    e.paper_id,
    e.task_id,
    e.dataset_id,
    e.model_name,
    e.harness ?? "",
  ].join("|");
}

/**
 * Fold separate evaluation rows that describe the same model on the same
 * leaderboard (differing only in `best_metric`) into one row whose `metrics`
 * object carries every configured value — e.g. LAMBADA Perplexity + Accuracy.
 */
export function mergeLeaderboardEvaluations(evals: Evaluation[]): MergedEvaluation[] {
  const groups = new Map<string, MergedEvaluation>();

  for (const e of evals) {
    const key = leaderboardRowKey(e);
    const existing = groups.get(key);
    if (!existing) {
      groups.set(key, {
        ...e,
        metrics: { ...(e.metrics || {}) },
        sourceEvaluationIds: [e.id],
        ranksByMetric:
          e.best_metric && e.best_rank != null ? { [e.best_metric]: e.best_rank } : {},
        parameterCount: e.num_parameters ?? null,
        hasParameterConflict: false,
      });
      continue;
    }

    existing.metrics = { ...existing.metrics, ...(e.metrics || {}) };
    existing.sourceEvaluationIds.push(e.id);
    if (e.best_metric && e.best_rank != null) {
      existing.ranksByMetric[e.best_metric] = e.best_rank;
    }
    if (e.num_parameters != null && !existing.hasParameterConflict) {
      if (existing.parameterCount === null) {
        existing.parameterCount = e.num_parameters;
      } else if (existing.parameterCount !== e.num_parameters) {
        existing.parameterCount = null;
        existing.hasParameterConflict = true;
      }
    }
  }

  return Array.from(groups.values());
}

/**
 * Apply the parameter-size control to already merged display entries. Unknown
 * and conflicting counts remain visible under All, but cannot be compared
 * against a numeric size ceiling.
 */
export function filterLeaderboardByParameterCount(
  entries: MergedEvaluation[],
  maxParametersExclusive: number | undefined,
): MergedEvaluation[] {
  if (maxParametersExclusive === undefined) return entries;
  return entries.filter(
    (entry) => entry.parameterCount !== null && entry.parameterCount < maxParametersExclusive,
  );
}

export function evaluationMatchesHighlight(e: MergedEvaluation, highlightEvalId?: string): boolean {
  if (!highlightEvalId) return false;
  return e.id === highlightEvalId || e.sourceEvaluationIds.includes(highlightEvalId);
}

export function storedRankForMetric(e: MergedEvaluation, metric: string): number {
  return e.ranksByMetric[metric] ?? e.best_rank ?? 9999;
}

/**
 * Compute the SOTA progression (running best) from evaluations sorted by
 * paper.published. Mirrors the v1 Benchmark.tsx logic, but ranks SOTA by the
 * currently selected metric's value + direction rather than by the row's
 * stored `best_rank` (which only describes the row's own `best_metric`
 * leaderboard, so it doesn't match alternate metric tabs like Recall on a
 * benchmark whose primary metric is F1).
 */
export function computeSeries(
  evals: Evaluation[],
  bestMetric: string,
  arrow: "↑" | "↓",
): { points: ChartPoint[]; sota: number; sotaModel: string } {
  if (evals.length === 0) return { points: [], sota: 0, sotaModel: "" };

  // Sort by published date ascending; require numeric values for the metric.
  const items = evals
    .map((e) => {
      const value = parseMetricValue(e.metrics?.[bestMetric]);
      const date = e.evaluated_on || e.paper_published_date || "";
      return { eval: e, value, date };
    })
    .filter((x): x is { eval: Evaluation; value: number; date: string } =>
      x.value !== null && !!x.date,
    )
    .sort((a, b) => a.date.localeCompare(b.date));

  const points: ChartPoint[] = [];
  let runningBest: number | null = null;
  for (const it of items) {
    const better = runningBest == null
      ? true
      : arrow === "↓"
        ? it.value < runningBest
        : it.value > runningBest;
    if (better) runningBest = it.value;
    points.push({
      value: it.value,
      date: it.date,
      dateLabel: it.date.slice(0, 7),
      modelName: it.eval.model_name || "",
      paperTitle: it.eval.paper_title || "",
      paperRouteId: it.eval.paper_arxiv_id || it.eval.paper_id || null,
      isSota: better,
    });
  }

  // Headline SOTA is the best value for the currently selected metric.
  // We sort all evals that have a numeric value for `bestMetric` by the
  // metric's direction, so secondary metrics like Recall/Precision get the
  // right top row instead of always echoing the F1 leader.
  const ranked = evals
    .map((e) => ({ eval: e, value: parseMetricValue(e.metrics?.[bestMetric]) }))
    .filter((x): x is { eval: Evaluation; value: number } => x.value !== null)
    .sort((a, b) => (arrow === "↓" ? a.value - b.value : b.value - a.value));

  const top = ranked[0];
  const sota = top?.value ?? 0;
  const sotaModel = top?.eval.model_name || top?.eval.paper_title || "";

  return { points, sota, sotaModel };
}

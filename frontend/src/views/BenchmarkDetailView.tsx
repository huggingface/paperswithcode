import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api";
import type { Evaluation, LeaderboardMetric, MetricDirections, Task } from "@/lib/api";
import { usePreferences } from "@/lib/preferencesContext";
import { formatMetricValue } from "@/lib/utils";
import { copyNodeAsPng } from "@/lib/copyScreenshot";
import { selectLeaderboardEvaluations } from "@/lib/leaderboardEvaluations";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Alert, AlertDescription } from "@/components/ui/alert";
import LatexTitle from "@/components/LatexTitle";
import { Icon } from "@/components";
import ClosedSourceEvalBadge from "@/components/ClosedSourceEvalBadge";
import ExternalSourceEvalBadge from "@/components/ExternalSourceEvalBadge";
import BenchmarkTrendSparkline from "@/components/BenchmarkTrendSparkline";
import { useToast } from "@/hooks/use-toast";

/** Cap how many metric columns we render in the leaderboard at once. The
 *  View dropdown still lists every configured metric — picking one outside
 *  the visible set promotes it to `activeMetric`, which guarantees the sort
 *  column is always shown (see `visibleMetrics` below). */
const MAX_METRIC_COLUMNS = 5;

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

interface ChartPoint {
  value: number;
  date: string;
  dateLabel: string;
  modelName: string;
  paperTitle: string;
  paperRouteId: string | null;
  isSota: boolean;
}

interface BenchmarkChartProps {
  points: ChartPoint[];
  metric: string;
}

function parseChartDateMs(date: string): number {
  const normalized = date.length === 7 ? `${date}-01` : date;
  const t = new Date(normalized).getTime();
  return Number.isFinite(t) ? t : 0;
}

const CHART_MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

interface ChartTimeTick {
  timestamp: number;
  key: string;
  label: string;
}

function chartDateParts(ms: number): { year: number; month: number } {
  const d = new Date(ms);
  return { year: d.getFullYear(), month: d.getMonth() };
}

/** Calendar-aware x-axis ticks: every year/month in range, with stepping only for very long spans. */
function buildChartTimeTicks(xMin: number, xMax: number): ChartTimeTick[] {
  if (xMin === xMax) {
    const { year, month } = chartDateParts(xMin);
    return [{
      timestamp: new Date(year, month, 1).getTime(),
      key: `${year}-${month}`,
      label: `${CHART_MONTH_LABELS[month]} ${year}`,
    }];
  }

  const start = chartDateParts(xMin);
  const end = chartDateParts(xMax);

  if (start.year === end.year) {
    const monthCount = end.month - start.month + 1;
    let step = 1;
    const maxMonthTicks = 12;
    if (monthCount > maxMonthTicks) {
      step = Math.ceil(monthCount / maxMonthTicks);
    }
    const ticks: ChartTimeTick[] = [];
    for (let month = start.month; month <= end.month; month += step) {
      ticks.push({
        timestamp: new Date(start.year, month, 1).getTime(),
        key: `${start.year}-${month}`,
        label: monthCount <= 3
          ? `${CHART_MONTH_LABELS[month]} ${start.year}`
          : CHART_MONTH_LABELS[month],
      });
    }
    return ticks;
  }

  const yearCount = end.year - start.year + 1;
  let step = 1;
  const maxYearTicks = 12;
  if (yearCount > maxYearTicks) {
    step = Math.ceil(yearCount / maxYearTicks);
  }
  const ticks: ChartTimeTick[] = [];
  for (let year = start.year; year <= end.year; year += step) {
    ticks.push({
      timestamp: new Date(year, 0, 1).getTime(),
      key: String(year),
      label: String(year),
    });
  }
  return ticks;
}

// Always plots raw values: larger values appear higher on the Y-axis, smaller
// values appear lower, regardless of whether the metric is higher- or
// lower-is-better. Direction only affects which points `computeSeries` marks
// as SOTA, not the visual orientation of the chart.
const BenchmarkChart: React.FC<BenchmarkChartProps> = ({ points: dataPoints, metric }) => {
  const navigate = useNavigate();
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const W = 880;
  const H = 320;
  const padL = 60;
  const padR = 30;
  const padT = 40;
  const padB = 50;
  const values = dataPoints.map((d) => d.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const timestamps = dataPoints.map((d) => parseChartDateMs(d.date));
  const xMin = Math.min(...timestamps);
  const xMax = Math.max(...timestamps);
  const xSpan = xMax - xMin || 1;
  const xForTime = (t: number) =>
    xMin === xMax ? padL + innerW / 2 : padL + ((t - xMin) / xSpan) * innerW;
  const positioned = dataPoints.map((dp, idx) => {
    const x = xForTime(parseChartDateMs(dp.date));
    const norm = (dp.value - min) / range;
    const y = padT + innerH * (1 - norm);
    return { x, y, data: dp, idx };
  });
  const sotaPositioned = positioned.filter((p) => p.data.isSota);
  let path = "";
  if (sotaPositioned.length >= 2) {
    path = `M${sotaPositioned[0].x},${sotaPositioned[0].y}`;
    for (let i = 1; i < sotaPositioned.length; i++) {
      const p0 = sotaPositioned[i - 1];
      const p1 = sotaPositioned[i];
      const cx = (p0.x + p1.x) / 2;
      path += ` C${cx},${p0.y} ${cx},${p1.y} ${p1.x},${p1.y}`;
    }
  }
  // Model-name labels above the highlighted SOTA dots (legacy PapersWithCode
  // look). Greedily de-cluttered left-to-right so labels never overlap each
  // other, clamped to stay inside the plot (out of the y-axis gutter), and the
  // latest SOTA point is always reserved a slot since it's the current best.
  type SotaLabel = { x: number; y: number; text: string; anchor: "start" | "middle" | "end" };
  const labelCharW = 5.4;
  const labelGap = 8;
  const labelDotGap = 9;
  const labelBox = (p: (typeof sotaPositioned)[number]): (SotaLabel & { left: number; right: number }) | null => {
    const raw = p.data.modelName || p.data.paperTitle || "";
    if (!raw) return null;
    const text = raw.length > 22 ? raw.slice(0, 21) + "…" : raw;
    const w = text.length * labelCharW;
    let left = p.x - w / 2;
    let right = p.x + w / 2;
    let anchor: SotaLabel["anchor"] = "middle";
    if (left < padL) {
      left = padL;
      right = padL + w;
      anchor = "start";
    } else if (right > W - padR) {
      right = W - padR;
      left = right - w;
      anchor = "end";
    }
    const x = anchor === "start" ? padL : anchor === "end" ? W - padR : p.x;
    return { x, y: p.y - labelDotGap, text, anchor, left, right };
  };
  const sotaLabels: SotaLabel[] = [];
  // Reserve the latest SOTA point's label first so it's never dropped.
  const reserved = sotaPositioned.length > 0 ? labelBox(sotaPositioned[sotaPositioned.length - 1]) : null;
  let lastLabelRight = -Infinity;
  for (let i = 0; i < sotaPositioned.length - 1; i++) {
    const box = labelBox(sotaPositioned[i]);
    if (!box) continue;
    if (box.left < lastLabelRight + labelGap) continue;
    if (reserved && box.right > reserved.left - labelGap) continue;
    lastLabelRight = box.right;
    sotaLabels.push({ x: box.x, y: box.y, text: box.text, anchor: box.anchor });
  }
  if (reserved) sotaLabels.push({ x: reserved.x, y: reserved.y, text: reserved.text, anchor: reserved.anchor });

  const timeAxisTicks = buildChartTimeTicks(xMin, xMax);
  const tickCount = 5;

  const clearHover = (i: number) => setHoverIdx((cur) => (cur === i ? null : cur));
  const handleClick = (routeId: string | null) => {
    if (routeId) navigate(`/paper/${routeId}`);
  };

  const renderDotInteraction = (
    p: (typeof positioned)[number],
    visible: React.ReactNode,
  ) => {
    const label = p.data.modelName || p.data.paperTitle || "Unknown model";
    const ariaLabel = `${label}: ${formatMetricValue(p.data.value)} on ${p.data.dateLabel}`;
    const clickable = !!p.data.paperRouteId;
    return (
      <g key={p.idx}>
        {visible}
        <circle
          cx={p.x}
          cy={p.y}
          r="10"
          fill="transparent"
          style={{ cursor: clickable ? "pointer" : "default", outline: "none" }}
          tabIndex={0}
          role={clickable ? "link" : "img"}
          aria-label={ariaLabel}
          onMouseEnter={() => setHoverIdx(p.idx)}
          onMouseLeave={() => clearHover(p.idx)}
          onFocus={() => setHoverIdx(p.idx)}
          onBlur={() => clearHover(p.idx)}
          onClick={() => handleClick(p.data.paperRouteId)}
          onKeyDown={(e) => {
            if (clickable && (e.key === "Enter" || e.key === " ")) {
              e.preventDefault();
              handleClick(p.data.paperRouteId);
            }
          }}
        >
          <title>{ariaLabel}</title>
        </circle>
      </g>
    );
  };

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
      <text
        x={padL - 38}
        y={padT + innerH / 2}
        fontSize="11"
        fontFamily="var(--mono)"
        fill="var(--ink-faint)"
        textAnchor="middle"
        transform={`rotate(-90 ${padL - 38} ${padT + innerH / 2})`}
      >
        {metric}
      </text>
      {Array.from({ length: tickCount }).map((_, i) => {
        const norm = i / (tickCount - 1);
        const y = padT + innerH * (1 - norm);
        const dataAtNorm = min + range * norm;
        return (
          <g key={i}>
            <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="var(--hairline)" strokeWidth="1" />
            <text x={padL - 10} y={y + 4} fontSize="11" fontFamily="var(--mono)" fill="var(--ink-faint)" textAnchor="end">
              {formatMetricValue(dataAtNorm)}
            </text>
          </g>
        );
      })}
      {timeAxisTicks.map((tick) => {
        const x = xForTime(tick.timestamp);
        return (
          <text
            key={tick.key}
            x={x}
            y={H - padB + 18}
            fontSize="11"
            fontFamily="var(--mono)"
            fill="var(--ink-soft)"
            textAnchor="middle"
          >
            {tick.label}
          </text>
        );
      })}
      {positioned
        .filter((p) => !p.data.isSota)
        .map((p) => {
          const isHover = hoverIdx === p.idx;
          return renderDotInteraction(
            p,
            <circle
              cx={p.x}
              cy={p.y}
              r={isHover ? 3 : 2}
              fill="var(--ink-faint)"
              opacity={isHover ? 1 : 0.45}
              style={{ transition: "r 0.12s ease, opacity 0.12s ease" }}
            />,
          );
        })}
      {path && (
        <path d={path} stroke="var(--accent)" strokeWidth="2" fill="none" strokeLinejoin="round" strokeLinecap="round" />
      )}
      {sotaPositioned.map((p) => {
        const isHover = hoverIdx === p.idx;
        return renderDotInteraction(
          p,
          <circle
            cx={p.x}
            cy={p.y}
            r={isHover ? 4.5 : 3}
            fill={isHover ? "var(--accent)" : "var(--bg-elevated)"}
            stroke="var(--accent)"
            strokeWidth="1.5"
            style={{ transition: "r 0.12s ease, fill 0.12s ease" }}
          />,
        );
      })}
      {sotaLabels.map((l, i) => (
        <text
          key={`label-${i}`}
          x={l.x}
          y={l.y}
          fontSize="9.5"
          fontFamily="var(--mono)"
          fill="var(--ink-soft)"
          textAnchor={l.anchor}
          pointerEvents="none"
          style={{ paintOrder: "stroke", stroke: "var(--bg-elevated)", strokeWidth: 3, strokeLinejoin: "round" }}
        >
          {l.text}
        </text>
      ))}
      {hoverIdx !== null && positioned[hoverIdx] && (() => {
        const p = positioned[hoverIdx];
        const rawLabel = p.data.modelName || p.data.paperTitle || "Unknown model";
        const name = rawLabel.length > 40 ? rawLabel.slice(0, 39) + "…" : rawLabel;
        const label = `${name}: ${formatMetricValue(p.data.value)}`;
        const charW = 6.6;
        const tooltipW = Math.max(120, Math.min(340, label.length * charW + 24));
        const tooltipH = 30;
        let tx = p.x - tooltipW / 2;
        if (tx < padL) tx = padL;
        if (tx + tooltipW > W - padR) tx = W - padR - tooltipW;
        const aboveDot = p.y - tooltipH - 14 >= padT;
        const ty = aboveDot ? p.y - tooltipH - 12 : p.y + 12;
        return (
          <g pointerEvents="none">
            <rect
              x={tx}
              y={ty}
              width={tooltipW}
              height={tooltipH}
              rx="6"
              ry="6"
              fill="var(--bg-elevated)"
              stroke="var(--hairline-strong)"
              strokeWidth="1"
              style={{ filter: "drop-shadow(0 2px 6px rgba(0,0,0,0.08))" }}
            />
            <text
              x={tx + 12}
              y={ty + 19}
              fontSize="12"
              fontFamily="var(--sans)"
              fill="var(--ink)"
              fontWeight={500}
            >
              {label}
            </text>
          </g>
        );
      })()}
    </svg>
  );
};

/**
 * Parse a stored metric value into a number. Handles "88.55 ± 0.04" style
 * strings (we keep the central estimate and drop the uncertainty), plain
 * numeric strings, and already-numeric values. Returns null when the value
 * isn't usable for comparisons so callers can push those rows to the end.
 */
function parseMetricValue(raw: string | number | undefined | null): number | null {
  if (raw == null) return null;
  if (typeof raw === "number") return Number.isFinite(raw) ? raw : null;
  const s = raw.includes("±") ? raw.split("±")[0].trim() : raw.trim();
  const n = parseFloat(s);
  return Number.isFinite(n) ? n : null;
}

type MergedEvaluation = Evaluation & {
  /** Source evaluation ids folded into this display row. */
  sourceEvaluationIds: string[];
  /** Per-metric stored ranks from the underlying evaluation rows. */
  ranksByMetric: Record<string, number>;
};

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
function mergeLeaderboardEvaluations(evals: Evaluation[]): MergedEvaluation[] {
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
      });
      continue;
    }

    existing.metrics = { ...existing.metrics, ...(e.metrics || {}) };
    existing.sourceEvaluationIds.push(e.id);
    if (e.best_metric && e.best_rank != null) {
      existing.ranksByMetric[e.best_metric] = e.best_rank;
    }
  }

  return Array.from(groups.values());
}

function evaluationMatchesHighlight(e: MergedEvaluation, highlightEvalId?: string): boolean {
  if (!highlightEvalId) return false;
  return e.id === highlightEvalId || e.sourceEvaluationIds.includes(highlightEvalId);
}

function storedRankForMetric(e: MergedEvaluation, metric: string): number {
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
function computeSeries(
  evals: Evaluation[],
  bestMetric: string,
  arrow: "↑" | "↓",
): { points: ChartPoint[]; sota: number; sotaModel: string } {
  if (evals.length === 0) return { points: [], sota: 0, sotaModel: "" };

  // Sort by published date ascending; require numeric values for the metric.
  const items = evals
    .map((e) => {
      const value = parseMetricValue(e.metrics?.[bestMetric]);
      const date = e.paper_published_date || "";
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

interface CopyScreenshotButtonProps {
  /** Node to capture. Lazily resolved on click so the button stays usable
   *  even if the ref is attached after a render-skipping branch. */
  targetRef: React.RefObject<HTMLElement>;
  /** Surface name used in the failure toast (e.g. "leaderboard"). */
  label: string;
}

const CopyScreenshotButton: React.FC<CopyScreenshotButtonProps> = ({ targetRef, label }) => {
  const { toast } = useToast();
  const [status, setStatus] = useState<"idle" | "copying" | "copied">("idle");
  const resetTimer = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (resetTimer.current !== null) {
        window.clearTimeout(resetTimer.current);
      }
    };
  }, []);

  const handleClick = useCallback(async () => {
    const node = targetRef.current;
    if (!node) return;
    setStatus("copying");
    node.classList.add("is-capturing");
    // Force the browser to flush the style/layout change that reveals the
    // screenshot-only title, then wait one paint frame so html-to-image's
    // clone walk sees the post-toggle dimensions. Without this, the title
    // is missing on tall cards like the leaderboard table.
    void node.offsetHeight;
    await new Promise<void>((resolve) =>
      window.requestAnimationFrame(() => resolve()),
    );
    try {
      await copyNodeAsPng(node);
      setStatus("copied");
      toast({
        title: "Screenshot copied",
        description: `Image of the ${label} copied to your clipboard.`,
      });
      if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
      resetTimer.current = window.setTimeout(() => setStatus("idle"), 1500);
    } catch (err) {
      setStatus("idle");
      toast({
        title: "Copy failed",
        description:
          err instanceof Error && err.message
            ? err.message
            : "Could not copy the screenshot to your clipboard.",
        variant: "destructive",
      });
    } finally {
      node.classList.remove("is-capturing");
    }
  }, [targetRef, label, toast]);

  const text = status === "copied" ? "Copied" : status === "copying" ? "Copying…" : "Copy image";

  return (
    <button
      type="button"
      className="bm-copy-btn"
      onClick={handleClick}
      disabled={status === "copying"}
      aria-label={`Copy ${label} screenshot to clipboard`}
      title={`Copy ${label} screenshot to clipboard`}
    >
      <Icon name="copy" size={11} />
      {text}
    </button>
  );
};

const BenchmarkDetailView: React.FC = () => {
  const { datasetSlug } = useParams<{ datasetSlug: string }>();
  const [searchParams] = useSearchParams();
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
  const { preferences, setHideClosedSourceEvals } = usePreferences();
  const [bestMetric, setBestMetric] = useState<string | undefined>(undefined);
  const highlightRowRef = useRef<HTMLTableRowElement | null>(null);
  const didScrollToHighlight = useRef(false);
  const chartCardRef = useRef<HTMLDivElement | null>(null);
  const leaderboardCardRef = useRef<HTMLDivElement | null>(null);

  // Fetching the dataset with `include_paper=true` collapses the previous
  // dataset → paper waterfall into a single round trip.  See PLAN.md §5.
  const datasetQ = useQuery({
    queryKey: ["dataset", datasetSlug, "with-paper"],
    queryFn: () => apiClient.getDatasetBySlug(datasetSlug!, { include_paper: true }),
    enabled: !!datasetSlug,
    staleTime: 10 * 60 * 1000,
  });

  // Fetch every evaluation on this dataset once. Metric switching is purely
  // a UI concern (column choice, sort key, SOTA computation), so we must not
  // pass `bestMetric` as an API filter — the backend filters on the row's
  // `best_metric` column, which would drop rows whose primary metric is
  // different from the tab the user clicked (e.g. an F1-primary row that
  // also carries Recall/Precision values).
  const evalsQ = useQuery({
    queryKey: ["dataset-evals", datasetQ.data?.id],
    queryFn: () => apiClient.getEvaluationsByDataset(datasetQ.data!.id),
    enabled: !!datasetQ.data?.id,
    staleTime: 5 * 60 * 1000,
  });

  const datasetTasksQ = useQuery<Task[]>({
    queryKey: ["dataset-tasks", datasetQ.data?.id],
    queryFn: () => apiClient.getDatasetTasks(datasetQ.data!.id),
    enabled: !!datasetQ.data?.id,
    staleTime: 10 * 60 * 1000,
  });

  const directionsQ = useQuery<MetricDirections>({
    queryKey: ["metric-directions"],
    queryFn: () => apiClient.getMetricDirections(),
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
      apiClient.getTrendingBenchmarks(currentTaskId!, {
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
    queryFn: () => apiClient.getLeaderboardMetrics(datasetQ.data!.id, currentTaskId!),
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
      for (const metric of Object.keys(e.metrics || {})) {
        if (configuredMetrics.length && !allowedMetrics.includes(metric)) continue;
        counts.set(metric, (counts.get(metric) || 0) + 1);
      }
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

  const activeMetric = bestMetric || highlightEval?.best_metric || defaultMetric;
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

  // Subset of `orderedMetrics` actually rendered as table columns, capped at
  // `MAX_METRIC_COLUMNS`. Since `activeMetric` leads, the active/default
  // metric is always shown first and never hidden by the cap.
  const visibleMetrics = useMemo(() => {
    if (orderedMetrics.length === 0) return activeMetric ? [activeMetric] : [];
    return orderedMetrics.slice(0, MAX_METRIC_COLUMNS);
  }, [orderedMetrics, activeMetric]);

  const { points: chartPoints, sota, sotaModel } = useMemo(
    () => computeSeries(mergedTaskEvals, activeMetric, arrow),
    [mergedTaskEvals, activeMetric, arrow],
  );

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
  const sortedRows = mergedTaskEvals.slice().sort((a, b) => {
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

        <div className="bm-hero-row">
          <div className="bm-hero-copy">
            <h1 className="bm-title">{dataset.name}</h1>
            <div className="bm-subtitle">
              <span>
                {activeMetric && (
                  <>
                    <span className="metric-tag">{activeMetric}</span>
                    <span style={{ color: "var(--hairline-strong)", margin: "0 8px" }}>·</span>
                  </>
                )}
                {sotaModel ? (
                  <span>
                    Best: <span className="best-name">{formatMetricValue(sota)}</span> by <span className="best-name" style={{ fontStyle: "normal" }}>{sotaModel}</span>
                  </span>
                ) : (
                  <span>{sortedRows.length} evaluations</span>
                )}
              </span>
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
          </div>

          {benchmarkTrend && (
            <aside className="bm-benchmark-trend" aria-label={`${dataset.name} reporting trend`}>
              <div className="bm-benchmark-trend-head">
                <span>Reporting activity</span>
                <span>{benchmarkTrendsQ.data?.recent_days || 90} days</span>
              </div>
              <BenchmarkTrendSparkline
                history={benchmarkTrend.history}
                benchmarkName={benchmarkTrend.name}
              />
              <div className="bm-benchmark-trend-summary">
                <span>
                  <strong>{benchmarkTrend.recent_paper_count}</strong>{" "}
                  {benchmarkTrend.recent_paper_count === 1 ? "paper" : "papers"} reporting
                </span>
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
              </div>
              {primaryTask && (
                <Link
                  className="bm-benchmark-trend-link"
                  to={`/tasks/${primaryTask.slug || primaryTask.id}`}
                >
                  View {primaryTask.name} benchmarks →
                </Link>
              )}
            </aside>
          )}
        </div>

        {dataset.description && (
          <p style={{ fontFamily: "var(--serif)", color: "var(--ink-soft)", maxWidth: 760, marginBottom: 16 }}>
            {dataset.description}
          </p>
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
                href={dataset.paper_url}
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

        {chartPoints.filter((p) => p.isSota).length >= 2 && (
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
                      onChange={(e) => setBestMetric(e.target.value)}
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
              All models over time · highlighted dots track the running best · hover for the model · click to open the paper
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
                    onChange={(e) => setBestMetric(e.target.value)}
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
              <CopyScreenshotButton targetRef={leaderboardCardRef} label="leaderboard" />
            </div>
          </div>
          {evalsQ.isLoading ? (
            <div style={{ padding: 16 }}>
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full mb-2" />
              ))}
            </div>
          ) : sortedRows.length === 0 ? (
            <div className="no-results">No evaluations submitted yet.</div>
          ) : (
            <div className="bm-table-scroll">
            <table className="bm-table">
              <thead>
                <tr>
                  <th className="col-rank">Rank</th>
                  <th className="col-model">Model</th>
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
                          onClick={() => setBestMetric(m)}
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
                            <Link to={`/paper/${paperRouteId}`}>
                              {renderBenchmarkPaperTitle(e.paper_title, paperLabel)}
                            </Link>
                          ) : (
                            renderBenchmarkPaperTitle(e.paper_title, paperLabel)
                          )}
                        </td>
                        <td className="col-year">{e.paper_published_date?.slice(0, 4) || "—"}</td>
                      </tr>
                    );
                  });
                })()}
              </tbody>
            </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default BenchmarkDetailView;

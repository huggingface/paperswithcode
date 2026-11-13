import React, { useId, useState } from "react";
import { useNavigate } from "react-router-dom";

import { formatMetricValue } from "@/lib/utils";
import type { ChartPoint } from "@/lib/benchmarkLeaderboard";

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
  // Halo via filter, not a text stroke: browsers paint a stroked label's
  // stroke in the find-in-page highlight color, turning matches into blobs.
  const labelHaloId = `${useId()}-label-halo`;
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
      <defs>
        <filter id={labelHaloId} x="-10%" y="-30%" width="120%" height="160%">
          <feMorphology in="SourceAlpha" operator="dilate" radius="1.5" result="halo" />
          <feFlood style={{ floodColor: "var(--bg-elevated)" }} />
          <feComposite in2="halo" operator="in" />
          <feMerge>
            <feMergeNode />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
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
          filter={`url(#${labelHaloId})`}
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

export default BenchmarkChart;

import { useState } from "react";
import type { BenchmarkTrendPoint } from "@/lib/api";

interface BenchmarkTrendSparklineProps {
  history: BenchmarkTrendPoint[];
  benchmarkName: string;
  interactive?: boolean;
}

const WIDTH = 112;
const HEIGHT = 42;
const PADDING_X = 5;
const PADDING_Y = 5;
const shortMonthFormatter = new Intl.DateTimeFormat("en", {
  month: "short",
  timeZone: "UTC",
});

const formatRange = (startDate: string, endDate: string) => {
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  if (start.getUTCMonth() === end.getUTCMonth()) {
    return `${shortMonthFormatter.format(start)} ${start.getUTCDate()}–${end.getUTCDate()}`;
  }
  return `${shortMonthFormatter.format(start)} ${start.getUTCDate()}–${shortMonthFormatter.format(end)} ${end.getUTCDate()}`;
};

const BenchmarkTrendSparkline = ({
  history,
  benchmarkName,
  interactive = false,
}: BenchmarkTrendSparklineProps) => {
  const [activePoint, setActivePoint] = useState<number | null>(null);
  const values = history.map((point) => point.paper_count);
  const maximum = Math.max(1, ...values);
  const chartWidth = WIDTH - PADDING_X * 2;
  const chartHeight = HEIGHT - PADDING_Y * 2;
  const step = values.length > 1 ? chartWidth / (values.length - 1) : 0;
  const coordinates = values.map((value, index) => ({
    x: PADDING_X + step * index,
    y: PADDING_Y + chartHeight - (value / maximum) * chartHeight,
  }));
  const points = coordinates.map(({ x, y }) => `${x},${y}`).join(" ");
  const areaPoints = coordinates.length
    ? `${PADDING_X},${HEIGHT - PADDING_Y} ${points} ${
        coordinates[coordinates.length - 1].x
      },${HEIGHT - PADDING_Y}`
    : "";
  const total = values.reduce((sum, value) => sum + value, 0);
  const tooltipWidth = 49;
  const tooltipHeight = 14;
  const tooltip = activePoint == null ? null : coordinates[activePoint];
  const tooltipX = tooltip
    ? Math.min(
        WIDTH - PADDING_X - tooltipWidth,
        Math.max(PADDING_X, tooltip.x - tooltipWidth / 2),
      )
    : 0;
  const tooltipY = tooltip
    ? tooltip.y > HEIGHT / 2
      ? tooltip.y - tooltipHeight - 3
      : tooltip.y + 3
    : 0;

  return (
    <svg
      className={`benchmark-trend-sparkline${interactive ? " is-interactive" : ""}`}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role={interactive ? "group" : "img"}
      aria-label={`${benchmarkName}: ${total} reporting papers across the displayed trend history`}
    >
      <title>
        {benchmarkName}: {total} reporting papers across the displayed trend history
      </title>
      <line
        className="benchmark-trend-axis"
        x1={PADDING_X}
        y1={HEIGHT - PADDING_Y}
        x2={WIDTH - PADDING_X}
        y2={HEIGHT - PADDING_Y}
      />
      <line
        className="benchmark-trend-axis"
        x1={PADDING_X}
        y1={PADDING_Y}
        x2={PADDING_X}
        y2={HEIGHT - PADDING_Y}
      />
      {areaPoints && <polygon className="benchmark-trend-area" points={areaPoints} />}
      {points && <polyline className="benchmark-trend-line" points={points} />}
      {interactive
        ? coordinates.map(({ x, y }, index) => (
            <g
              key={`${history[index].start_date}-${history[index].end_date}`}
              className="benchmark-trend-point"
              tabIndex={0}
              role="img"
              aria-label={`${formatRange(history[index].start_date, history[index].end_date)}: ${history[index].paper_count} ${
                history[index].paper_count === 1 ? "paper" : "papers"
              }`}
              onMouseEnter={() => setActivePoint(index)}
              onMouseLeave={() => setActivePoint(null)}
              onFocus={() => setActivePoint(index)}
              onBlur={() => setActivePoint(null)}
            >
              <circle className="benchmark-trend-point-hit" cx={x} cy={y} r="5" />
              <circle className="benchmark-trend-point-mark" cx={x} cy={y} r="1.8" />
            </g>
          ))
        : coordinates.length > 0 && (
            <circle
              className="benchmark-trend-dot"
              cx={coordinates[coordinates.length - 1].x}
              cy={coordinates[coordinates.length - 1].y}
              r="2.6"
            />
          )}
      {tooltip && activePoint != null && (
        <g className="benchmark-trend-tooltip" pointerEvents="none">
          <rect
            x={tooltipX}
            y={tooltipY}
            width={tooltipWidth}
            height={tooltipHeight}
            rx="2"
          />
          <text x={tooltipX + 3} y={tooltipY + 5.4}>
            {formatRange(
              history[activePoint].start_date,
              history[activePoint].end_date,
            )}
          </text>
          <text className="benchmark-trend-tooltip-value" x={tooltipX + 3} y={tooltipY + 11}>
            {history[activePoint].paper_count}{" "}
            {history[activePoint].paper_count === 1 ? "paper" : "papers"}
          </text>
        </g>
      )}
    </svg>
  );
};

export default BenchmarkTrendSparkline;

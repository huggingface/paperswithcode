import React from "react";

import type { TrendPoint } from "@/lib/api/stats";

const formatTrendMonth = (month: string): string => {
  const match = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(month);
  if (!match) return month;

  const [, year, monthNumber] = match;
  const names = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  return `${names[Number(monthNumber) - 1]} '${year.slice(2)}`;
};

interface TrendChartProps {
  id: string;
  data: TrendPoint[];
  color: string;
  yTicks: number[];
  yLabel: string;
  xLabel: string;
}

const W = 980;
const H = 400;
const PAD_L = 62;
const PAD_R = 26;
const PAD_T = 30;
const PAD_B = 58;
const PLOT_W = W - PAD_L - PAD_R;
const PLOT_H = H - PAD_T - PAD_B;
const BOTTOM = PAD_T + PLOT_H;

const smoothPath = (points: Array<[number, number]>): string => {
  if (points.length < 3) {
    return points
      .map((point, index) => `${index ? "L" : "M"}${point[0]} ${point[1]}`)
      .join(" ");
  }

  let path = `M${points[0][0]} ${points[0][1]}`;
  for (let index = 0; index < points.length - 1; index += 1) {
    const previous = points[index - 1] ?? points[index];
    const current = points[index];
    const next = points[index + 1];
    const following = points[index + 2] ?? next;
    const control1X = current[0] + (next[0] - previous[0]) / 6;
    const control1Y = current[1] + (next[1] - previous[1]) / 6;
    const control2X = next[0] - (following[0] - current[0]) / 6;
    const control2Y = next[1] - (following[1] - current[1]) / 6;
    path += ` C ${control1X} ${control1Y} ${control2X} ${control2Y} ${next[0]} ${next[1]}`;
  }
  return path;
};

const tickTextStyle: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 12,
  fill: "var(--ink-faint)",
};

const axisTitleStyle: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: "0.14em",
  fill: "var(--ink-faint)",
  textTransform: "uppercase",
};

const TrendChart: React.FC<TrendChartProps> = ({
  id,
  data,
  color,
  yTicks,
  yLabel,
  xLabel,
}) => {
  const [hoveredIndex, setHoveredIndex] = React.useState<number | null>(null);

  const count = data.length;
  const yMax = yTicks[yTicks.length - 1];
  const xAt = (index: number) =>
    PAD_L + PLOT_W * (count === 1 ? 0 : index / (count - 1));
  const yAt = (value: number) => PAD_T + PLOT_H * (1 - value / yMax);

  if (count === 0) return null;

  const points = data.map(
    (point, index): [number, number] => [xAt(index), yAt(point.percent)],
  );
  const linePath = smoothPath(points);
  const areaPath = `${linePath} L ${xAt(count - 1)} ${BOTTOM} L ${PAD_L} ${BOTTOM} Z`;
  const labelStep = count <= 12 ? 1 : Math.ceil(count / 8);

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const relativeX = ((event.clientX - rect.left) / rect.width) * W;
    const pointSpacing = count > 1 ? PLOT_W / (count - 1) : PLOT_W;
    const index = Math.max(
      0,
      Math.min(count - 1, Math.round((relativeX - PAD_L) / pointSpacing)),
    );
    setHoveredIndex(index);
  };

  const gradientId = `trend-gradient-${id}`;

  return (
    <figure className="trend-chart">
      <div className="trend-chart-visual">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          role="img"
          aria-label={`${yLabel} by ${xLabel.toLowerCase()}, from ${formatTrendMonth(data[0].month)} (${data[0].percent}%) to ${formatTrendMonth(data[count - 1].month)} (${data[count - 1].percent}%)`}
          style={{ display: "block", overflow: "visible", cursor: "crosshair" }}
          onPointerMove={onPointerMove}
          onPointerLeave={() => setHoveredIndex(null)}
        >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" style={{ stopColor: color, stopOpacity: 0.26 }} />
            <stop offset="100%" style={{ stopColor: color, stopOpacity: 0.02 }} />
          </linearGradient>
        </defs>

        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              x1={PAD_L}
              x2={W - PAD_R}
              y1={yAt(tick)}
              y2={yAt(tick)}
              stroke="var(--hairline)"
              strokeWidth={1}
            />
            <text
              x={PAD_L - 14}
              y={yAt(tick) + 4}
              textAnchor="end"
              style={tickTextStyle}
            >
              {tick}%
            </text>
          </g>
        ))}

        <path d={areaPath} fill={`url(#${gradientId})`} />
        <path
          d={linePath}
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {data.map((point, index) => {
          const isLast = index === count - 1;
          const isStepped =
            index % labelStep === 0 && count - 1 - index >= labelStep / 2;
          if (!isLast && !isStepped) return null;

          return (
            <text
              key={point.month}
              x={xAt(index)}
              y={BOTTOM + 24}
              textAnchor="middle"
              style={tickTextStyle}
            >
              {formatTrendMonth(point.month)}
            </text>
          );
        })}

        <text
          x={PAD_L + PLOT_W / 2}
          y={H - 4}
          textAnchor="middle"
          style={axisTitleStyle}
        >
          {xLabel}
        </text>
        <text
          transform={`translate(16 ${PAD_T + PLOT_H / 2}) rotate(-90)`}
          textAnchor="middle"
          style={axisTitleStyle}
        >
          {yLabel}
        </text>

        {hoveredIndex != null && (
          <>
            <line
              x1={xAt(hoveredIndex)}
              x2={xAt(hoveredIndex)}
              y1={PAD_T}
              y2={BOTTOM}
              stroke={color}
              strokeWidth={1}
              strokeDasharray="3 4"
              opacity={0.5}
            />
            <circle
              cx={xAt(hoveredIndex)}
              cy={yAt(data[hoveredIndex].percent)}
              r={5}
              fill="var(--bg)"
              stroke={color}
              strokeWidth={2}
            />
          </>
        )}
        </svg>

        {hoveredIndex != null && (
          <div
            style={{
              position: "absolute",
              left: `${(xAt(hoveredIndex) / W) * 100}%`,
              top: `${(yAt(data[hoveredIndex].percent) / H) * 100}%`,
              transform: "translate(-50%, calc(-100% - 14px))",
              background: "var(--bg-elevated)",
              border: "1px solid var(--hairline)",
              borderRadius: 6,
              boxShadow: "0 8px 26px rgba(0,0,0,.13)",
              padding: "7px 12px",
              pointerEvents: "none",
              whiteSpace: "nowrap",
              zIndex: 3,
            }}
          >
            <div
              style={{
                fontFamily: "var(--serif)",
                fontStyle: "italic",
                color: "var(--ink-faint)",
                fontSize: 13,
                marginBottom: 2,
              }}
            >
              {formatTrendMonth(data[hoveredIndex].month)}
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 7,
                fontFamily: "var(--mono)",
                fontWeight: 600,
                fontSize: 15,
                color: "var(--ink)",
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 2,
                  background: color,
                  display: "inline-block",
                }}
              />
              {data[hoveredIndex].percent}%
            </div>
          </div>
        )}
      </div>

      <details className="trend-chart-table">
        <summary
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11,
            letterSpacing: "0.04em",
            color: "var(--ink-faint)",
            cursor: "pointer",
          }}
        >
          View data table
        </summary>
        <table
          style={{
            marginTop: 8,
            borderCollapse: "collapse",
            fontFamily: "var(--mono)",
            fontSize: 12,
            color: "var(--ink-soft)",
          }}
        >
          <thead>
            <tr>
              <th style={{ textAlign: "left", padding: "3px 18px 3px 0" }}>
                {xLabel}
              </th>
              <th style={{ textAlign: "right", padding: "3px 0" }}>{yLabel}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((point) => (
              <tr key={point.month}>
                <td style={{ padding: "2px 18px 2px 0" }}>
                  {formatTrendMonth(point.month)}
                </td>
                <td style={{ textAlign: "right", padding: "2px 0" }}>
                  {point.percent}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
};

export default TrendChart;

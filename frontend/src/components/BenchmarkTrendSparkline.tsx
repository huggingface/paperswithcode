import type { BenchmarkTrendPoint } from "@/lib/api";

interface BenchmarkTrendSparklineProps {
  history: BenchmarkTrendPoint[];
  benchmarkName: string;
}

const WIDTH = 112;
const HEIGHT = 42;
const PADDING_X = 5;
const PADDING_Y = 5;

const BenchmarkTrendSparkline = ({
  history,
  benchmarkName,
}: BenchmarkTrendSparklineProps) => {
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

  return (
    <svg
      className="benchmark-trend-sparkline"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
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
      {coordinates.length > 0 && (
        <circle
          className="benchmark-trend-dot"
          cx={coordinates[coordinates.length - 1].x}
          cy={coordinates[coordinates.length - 1].y}
          r="2.6"
        />
      )}
    </svg>
  );
};

export default BenchmarkTrendSparkline;

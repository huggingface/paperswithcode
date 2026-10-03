import { useRef } from "react";
import type { LeaderboardPresentation } from "@/lib/leaderboardPresentation";
import { Switch } from "@/components/ui/switch";
import BenchmarkChart from "@/components/benchmark/BenchmarkChart";
import CopyScreenshotButton from "@/components/benchmark/CopyScreenshotButton";

export default function BenchmarkProgression({
  model,
  datasetName,
  hideClosed,
  setHideClosed,
  setMetric,
}: {
  model: LeaderboardPresentation;
  datasetName: string;
  hideClosed: boolean;
  setHideClosed: (hide: boolean) => void;
  setMetric: (metric: string) => void;
}) {
  const chartCardRef = useRef<HTMLDivElement>(null);
  const {
    isInitialFilteredViewLoading,
    chartPoints,
    activeMetric,
    allowedMetrics,
    orderedMetrics,
    parameterBound,
  } = model;
  if (isInitialFilteredViewLoading || chartPoints.length === 0) return null;
  return (
    <div className="bm-card" ref={chartCardRef}>
      <div className="bm-card-screenshot-header" aria-hidden="true">
        <div className="bm-card-screenshot-title">
          <span className="bm-card-screenshot-eyebrow">Benchmark</span>
          <span className="bm-card-screenshot-name">{datasetName}</span>
        </div>
        <div className="bm-card-screenshot-brand">
          <span className="brand">
            <span className="brand-mark"></span>
            <span className="brand-name">
              Papers <em>With Code</em>
            </span>
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
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label
            className="bm-closed-toggle"
            title="Show or hide evaluations of closed-source models"
          >
            <Switch
              className="bm-closed-toggle-switch"
              checked={!hideClosed}
              onCheckedChange={(checked) => {
                void setHideClosed(!checked);
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
        {parameterBound === undefined ? "All models" : "Filtered models"} over
        time · highlighted dots track the running best · hover for the model ·
        click to open the paper
      </div>
    </div>
  );
}

import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { LeaderboardPresentation } from "@/lib/leaderboardPresentation";
import { formatMetricValue } from "@/lib/utils";
import { formatParameterCount } from "@/lib/benchmarkLeaderboard";
import LatexTitle from "@/components/LatexTitle";
import ClosedSourceEvalBadge from "@/components/ClosedSourceEvalBadge";
import ExternalSourceEvalBadge from "@/components/ExternalSourceEvalBadge";

function renderBenchmarkPaperTitle(
  paperTitle: string | undefined,
  paperLabel: string | null,
): React.ReactNode {
  if (paperTitle) {
    return <LatexTitle title={paperTitle} />;
  }
  return paperLabel || "—";
}

export default function BenchmarkTable({
  model,
  showHarness,
  setMetric,
  highlightRowRef,
}: {
  model: LeaderboardPresentation;
  showHarness: boolean;
  setMetric: (metric: string) => void;
  highlightRowRef: React.RefObject<HTMLTableRowElement>;
}) {
  const { rows, visibleMetrics, activeMetric, arrow } = model;
  const [tableScrollElement, setTableScrollElement] =
    useState<HTMLDivElement | null>(null);
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
    if (tableScrollElement.firstElementChild)
      observer.observe(tableScrollElement.firstElementChild);
    updateOverflow();
    return () => observer.disconnect();
  }, [tableScrollElement]);
  return (
    <div
      ref={setTableScrollElement}
      className="bm-table-scroll"
      role="region"
      aria-label="Leaderboard metrics"
      tabIndex={0}
    >
      <table
        id="benchmark-leaderboard"
        className="bm-table"
        style={
          {
            "--bm-metric-count": visibleMetrics.length,
            "--bm-harness-count": showHarness ? 1 : 0,
          } as React.CSSProperties
        }
      >
        <colgroup>
          <col className="bm-width-rank" />
          <col className="bm-width-model" />
          <col className="bm-width-parameters" />
          {showHarness && <col className="bm-width-harness" />}
          {visibleMetrics.map((m) => (
            <col key={m} className="bm-width-metric" />
          ))}
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
                  aria-sort={
                    isActive
                      ? arrow === "↓"
                        ? "ascending"
                        : "descending"
                      : "none"
                  }
                >
                  <button
                    type="button"
                    className="bm-metric-header"
                    onClick={() => setMetric(m)}
                    aria-pressed={isActive}
                    title={`Sort by ${m}`}
                  >
                    {m}
                    {isActive ? ` ${arrow}` : ""}
                  </button>
                </th>
              );
            })}
            <th className="col-paper">Paper</th>
            <th className="col-year">Year</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ evaluation: e, rank, isHighlighted }) => {
            const paperRouteId = e.paper_arxiv_id || e.paper_id;
            const paperLabel =
              e.paper_title ||
              (e.paper_arxiv_id ? `arXiv:${e.paper_arxiv_id}` : null);
            return (
              <tr
                key={e.id}
                ref={isHighlighted ? highlightRowRef : undefined}
                className={isHighlighted ? "is-highlighted" : undefined}
              >
                <td className="col-rank">{rank ?? "—"}</td>
                <td className="col-model">
                  {isHighlighted && (
                    <span className="bm-row-marker" aria-hidden="true" />
                  )}
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
                    <ExternalSourceEvalBadge
                      sourceUrl={
                        e.source_url || e.external_source_url || e.result_url
                      }
                    />
                  )}
                </td>
                <td
                  className="col-parameters"
                  title={
                    e.parameterCount === null
                      ? undefined
                      : e.parameterCount.toLocaleString("en-US")
                  }
                  aria-label={
                    e.parameterCount === null
                      ? "Parameters unknown"
                      : `${e.parameterCount.toLocaleString("en-US")} parameters`
                  }
                >
                  {e.parameterCount === null
                    ? "—"
                    : formatParameterCount(e.parameterCount)}
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
                    <Link
                      to={`/paper/${paperRouteId}`}
                      title={e.paper_title || paperLabel || undefined}
                    >
                      {renderBenchmarkPaperTitle(e.paper_title, paperLabel)}
                    </Link>
                  ) : (
                    renderBenchmarkPaperTitle(e.paper_title, paperLabel)
                  )}
                </td>
                <td className="col-year">
                  {(e.evaluated_on || e.paper_published_date)?.slice(0, 4) ||
                    "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

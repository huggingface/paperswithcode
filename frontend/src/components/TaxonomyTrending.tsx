import React from "react";
import { Link } from "react-router-dom";
import { TrendingUp } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { TaxonomyView } from "@/hooks/useTaxonomyView";

export const TaxonomyViewTabs: React.FC<{
  view: TaxonomyView;
  onChange: (view: TaxonomyView) => void;
  allLabel: string;
}> = ({ view, onChange, allLabel }) => (
  <div className="sort-bar taxonomy-view-tabs">
    <div className="sort-options" role="tablist" aria-label="Directory view">
      {(
        [
          ["trending", "trending"],
          ["all", allLabel],
        ] as const
      ).map(([key, label]) => (
        <button
          key={key}
          type="button"
          role="tab"
          aria-selected={view === key}
          className={`sort-btn ${view === key ? "active" : ""}`}
          onClick={() => onChange(key)}
        >
          {label}
        </button>
      ))}
    </div>
  </div>
);

export interface TrendingTaxonomyItem {
  id: string;
  name: string;
  href: string;
  areaName?: string;
  recentPaperCount: number;
  shareLift: number;
}

/** Cross-area ranking of the tasks or methods gaining the most momentum. */
export const TrendingTaxonomyGrid: React.FC<{
  noun: "task" | "method";
  items?: TrendingTaxonomyItem[];
  recentDays?: number;
  baselineDays?: number;
  isLoading: boolean;
  error: unknown;
  mono?: boolean;
}> = ({ noun, items, recentDays = 30, baselineDays = 180, isLoading, error, mono }) => {
  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>Failed to load trending {noun}s. Please try again.</AlertDescription>
      </Alert>
    );
  }
  if (isLoading) {
    return (
      <div className="tag-grid">
        {Array.from({ length: 12 }).map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
    );
  }
  return (
    <section aria-label={`Trending ${noun}s`}>
      <p className="taxonomy-trending-note">
        {noun === "task" ? "Tasks" : "Methods"} across all areas whose share of papers in the
        last {recentDays} days grew the most against the preceding {baselineDays} days.
      </p>
      {items && items.length > 0 ? (
        <div className="tag-grid">
          {items.map((item, index) => (
            <Link key={item.id} to={item.href} className="tag-cell">
              <div className="name" style={mono ? { fontFamily: "var(--mono)", fontSize: 15 } : undefined}>
                <span className="taxonomy-trending-rank">{index + 1}</span>
                {item.name}
              </div>
              <div className="meta taxonomy-trending-meta">
                {item.areaName && (
                  <>
                    <span>{item.areaName}</span>
                    <span>·</span>
                  </>
                )}
                <span>
                  {item.recentPaperCount.toLocaleString()} papers / {recentDays}d
                </span>
                <span>·</span>
                <span
                  className="method-trend-score taxonomy-trending-lift"
                  title={`Share of recent papers is ${item.shareLift.toFixed(1)}× its baseline share`}
                >
                  <TrendingUp size={12} aria-hidden="true" />
                  {item.shareLift.toFixed(1)}×
                </span>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <p className="taxonomy-trending-note">No {noun}s are gaining momentum right now.</p>
      )}
    </section>
  );
};

import React from "react";
import { Link } from "react-router-dom";
import { TrendingUp } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
export interface TrendingTaxonomyItem {
  id: string;
  name: string;
  href: string;
  areaName?: string;
  recentPaperCount: number;
  shareLift: number;
}

/**
 * Cross-area ranking of the tasks or methods gaining the most momentum,
 * shown above the full area-by-area directory. Hidden when nothing qualifies.
 */
export const TrendingTaxonomyGrid: React.FC<{
  noun: "task" | "method";
  items?: TrendingTaxonomyItem[];
  recentDays?: number;
  baselineDays?: number;
  isLoading: boolean;
  error: unknown;
  mono?: boolean;
}> = ({ noun, items, recentDays = 30, baselineDays = 180, isLoading, error, mono }) => {
  if (!isLoading && !error && !items?.length) return null;
  return (
    <section id="trending" className="taxonomy-trending" aria-label={`Trending ${noun}s`}>
      <div className="taxonomy-trending-header">
        <h2>
          <TrendingUp size={22} aria-hidden="true" />
          Trending
        </h2>
        <p className="taxonomy-trending-note">
          {noun === "task" ? "Tasks" : "Methods"} across all areas whose share of papers in the
          last {recentDays} days grew the most against the preceding {baselineDays} days.
        </p>
      </div>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>Failed to load trending {noun}s.</AlertDescription>
        </Alert>
      ) : isLoading ? (
        <div className="tag-grid">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : (
        <div className="tag-grid">
          {items?.map((item, index) => (
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
      )}
    </section>
  );
};

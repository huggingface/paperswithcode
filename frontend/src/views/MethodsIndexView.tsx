import React, { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Flame } from "lucide-react";

import type { MethodIndexEntry } from "@/lib/api/catalog.types";
import { catalogApi } from "@/lib/api/catalog";
import { slugify } from "@/lib/slug";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { TaxonomySuggestionTile } from "@/components/TaxonomySuggestionTile";
import { TrendingTaxonomyGrid } from "@/components/TaxonomyTrending";

/**
 * Methods index — methods grouped by `area_id`, sorted by trend score desc
 * within each area. Backend areas are the single source of grouping truth.
 */
const MethodsIndexView: React.FC = () => {
  const areasQ = useQuery({
    queryKey: ["areas-all"],
    queryFn: () => catalogApi.listAreas({ page_size: 50, ordering: "name" }),
    staleTime: 10 * 60 * 1000,
  });

  // Use the compact directory projection so card rendering does not download
  // method descriptions, citations, image metadata, or other detail fields.
  const methodsQ = useQuery({
    queryKey: ["methods-all"],
    queryFn: async () => (await catalogApi.methodIndex()).results,
    staleTime: 10 * 60 * 1000,
  });
  const trendingQ = useQuery({
    queryKey: ["trending-methods-directory"],
    queryFn: () => catalogApi.trendingMethods({ limit: 12 }),
    staleTime: 10 * 60 * 1000,
  });

  const trendingItems = useMemo(() => {
    const areaNames = new Map((areasQ.data?.results ?? []).map((area) => [area.id, area.name]));
    return trendingQ.data?.results.map((method) => ({
      id: method.id,
      name: method.name,
      href: `/methods/${method.slug || method.id}`,
      areaName: method.area_id ? areaNames.get(method.area_id) : undefined,
      recentPaperCount: method.recent_paper_count,
      shareLift: method.share_lift,
    }));
  }, [trendingQ.data, areasQ.data]);

  const grouped = useMemo(() => {
    if (!methodsQ.data || !areasQ.data) return null;
    const byArea: Record<string, MethodIndexEntry[]> = {};
    methodsQ.data.forEach((m) => {
      const key = m.area_id ?? "_unassigned";
      (byArea[key] ||= []).push(m);
    });
    Object.values(byArea).forEach((arr) =>
      arr.sort(
        (a, b) =>
          (b.trend_score || 0) - (a.trend_score || 0) ||
          (b.paper_count || 0) - (a.paper_count || 0) ||
          a.name.localeCompare(b.name),
      ),
    );
    return byArea;
  }, [methodsQ.data, areasQ.data]);

  const trendingMethodIds = useMemo(() => {
    const ranked = (methodsQ.data || [])
      .filter((method) => (method.trend_score || 0) > 0)
      .sort((a, b) => (b.trend_score || 0) - (a.trend_score || 0));
    const topCount = Math.ceil(ranked.length * 0.25);
    return new Set(ranked.slice(0, topCount).map((method) => method.id));
  }, [methodsQ.data]);

  useEffect(() => {
    // Wait for the trending section above the areas so the offset is final.
    if (!areasQ.data || !methodsQ.data || trendingQ.isLoading || !window.location.hash) return;
    document
      .getElementById(window.location.hash.slice(1))
      ?.scrollIntoView({ block: "start" });
  }, [areasQ.data, methodsQ.data, trendingQ.isLoading]);

  if (areasQ.error || methodsQ.error) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Failed to load methods.</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            Methods <em>library</em>
          </h1>
          <div className="feed-subtitle">
            Common techniques used across AI research. Trend scores show papers
            using each method per 30 days, measured over the latest 90 days;
            the flame marks the top quartile.
          </div>
        </div>
      </div>

      <TrendingTaxonomyGrid
        noun="method"
        items={trendingItems}
        recentDays={trendingQ.data?.recent_days}
        baselineDays={trendingQ.data?.baseline_days}
        isLoading={trendingQ.isLoading}
        error={trendingQ.error}
        mono
      />

      {(areasQ.isLoading || methodsQ.isLoading) ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i}>
              <Skeleton className="h-8 w-1/3 mb-4" />
              <div className="tag-grid">
                {Array.from({ length: 8 }).map((__, j) => (
                  <Skeleton key={j} className="h-20" />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        areasQ.data?.results?.map((area) => {
          const methods = grouped?.[area.id] || [];
          if (methods.length === 0) return null;
          const totalPapers = methods.reduce((s, m) => s + (m.paper_count || 0), 0);
          return (
            <section
              key={area.id}
              id={`area-${slugify(area.name)}`}
              style={{ marginBottom: 48, scrollMarginTop: 80 }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: "6px 24px",
                  paddingBottom: 12,
                  borderBottom: "1px solid var(--hairline-strong)",
                }}
              >
                <div>
                  <h2
                    style={{
                      fontFamily: "var(--serif)",
                      fontSize: 26,
                      fontWeight: 500,
                      letterSpacing: "-0.02em",
                      marginBottom: 4,
                    }}
                  >
                    {area.name}
                  </h2>
                </div>
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--ink-faint)",
                    whiteSpace: "nowrap",
                  }}
                >
                  {methods.length} methods · {totalPapers.toLocaleString()} papers
                </div>
              </div>
              <div className="tag-grid">
                {methods.map((m) => (
                  <Link key={m.id} to={`/methods/${m.slug || m.id}`} className="tag-cell">
                    <div className="name" style={{ fontFamily: "var(--mono)", fontSize: 15 }}>
                      {m.name}
                      {trendingMethodIds.has(m.id) && (
                        <Flame
                          className="method-trending-icon"
                          size={15}
                          aria-label="Top quartile by recent method mentions"
                        />
                      )}
                    </div>
                    <div className="meta">
                      <span>{(m.paper_count ?? 0).toLocaleString()} papers</span>
                      {(m.trend_score ?? 0) > 0 && (
                        <>
                          <span>·</span>
                          <span className="method-trend-score">
                            {(m.trend_score ?? 0).toFixed(1)}/mo
                          </span>
                        </>
                      )}
                      {m.introduced_year != null && (
                        <>
                          <span>·</span>
                          <span>{m.introduced_year}</span>
                        </>
                      )}
                    </div>
                  </Link>
                ))}
                <TaxonomySuggestionTile kind="method" />
              </div>
            </section>
          );
        })
      )}
    </div>
  );
};

export default MethodsIndexView;

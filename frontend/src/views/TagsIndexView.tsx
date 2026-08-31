import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { catalogApi } from "@/lib/api/catalog";
import { chipColors, hueFromSlug } from "@/lib/colors";
import { displayTaskName } from "@/lib/transform";
import { slugify } from "@/lib/slug";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { TaxonomySuggestionTile } from "@/components/TaxonomySuggestionTile";

const taskKey = (value?: string) => value?.trim().toLowerCase().replace(/[\s_]+/g, "-") ?? "";

/**
 * Browse page: render the backend areas verbatim, each with their tasks.
 *
 * Uses the consolidated `/api/v1/areas/with-tasks/` endpoint, which returns
 * every area populated with its tasks (and aggregated paper counts) in one
 * round-trip, so this view can render the returned taxonomy directly.
 */
const TagsIndexView: React.FC = () => {
  const taxonomyQ = useQuery({
    queryKey: ["areas-with-tasks"],
    queryFn: () => catalogApi.areasWithTasks(),
    staleTime: 10 * 60 * 1000,
  });

  const visibleAreas = useMemo(() => {
    if (!taxonomyQ.data) return [];

    // General sits at the top as the broad catchall, then the modality areas
    // follow in a curated order, with "Other" at the end. Anything outside
    // this map falls after that (sorted alphabetically) so newly added areas
    // show up without code edits.
    const AREA_ORDER: Record<string, number> = {
      general: 0,
      vision: 1,
      video: 2,
      language: 3,
      audio: 4,
      other: 5,
    };
    const rank = (name: string) => AREA_ORDER[taskKey(name)] ?? 999;

    return [...taxonomyQ.data.results].sort((a, b) => {
      const ra = rank(a.name);
      const rb = rank(b.name);
      if (ra !== rb) return ra - rb;
      return a.name.localeCompare(b.name);
    });
  }, [taxonomyQ.data]);

  const totalTasks = useMemo(() => {
    return visibleAreas.reduce((s, area) => s + area.tasks.length, 0);
  }, [visibleAreas]);

  if (taxonomyQ.error) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Failed to load taxonomy. Please try again.</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            All <em>Domains</em>
          </h1>
          <div className="feed-subtitle">Browse research by area. Click any task to see trending work.</div>
        </div>
      </div>

      {taxonomyQ.isLoading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i}>
              <Skeleton className="h-8 w-1/3 mb-4" />
              <div className="tag-grid">
                {Array.from({ length: 6 }).map((__, j) => (
                  <Skeleton key={j} className="h-24" />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        visibleAreas.map((area) => {
          const tasks = area.tasks;
          if (tasks.length === 0) return null;
          const totalPapers = tasks.reduce((s, t) => s + (t.paper_count || 0), 0);
          return (
            <section
              key={area.id}
              id={`area-${slugify(area.name)}`}
              style={{ marginBottom: 48 }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  justifyContent: "space-between",
                  gap: 24,
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
                  {area.description && (
                    <div
                      style={{
                        fontFamily: "var(--serif)",
                        fontStyle: "italic",
                        fontSize: 13,
                        color: "var(--ink-soft)",
                      }}
                    >
                      {area.description}
                    </div>
                  )}
                </div>
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--ink-faint)",
                    whiteSpace: "nowrap",
                  }}
                >
                  {tasks.length} {tasks.length === 1 ? "task" : "tasks"} · {totalPapers.toLocaleString()} papers
                </div>
              </div>
              <div className="tag-grid">
                {tasks.map((t) => {
                  const slug = t.slug || "";
                  const c = chipColors(hueFromSlug(slug));
                  return (
                    <Link key={t.id} to={`/tasks/${slug}`} className="tag-cell">
                      <div className="name">
                        <span className="dot" style={{ background: c.dot }}></span>
                        {displayTaskName(t.name, slug)}
                      </div>
                      <div className="meta">
                        <span>{(t.paper_count ?? 0).toLocaleString()} papers</span>
                      </div>
                    </Link>
                  );
                })}
                <TaxonomySuggestionTile kind="task" />
              </div>
            </section>
          );
        })
      )}

      {totalTasks > 0 && (
        <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)", marginTop: 24 }}>
          {totalTasks} tasks across {visibleAreas.filter((area) => area.tasks.length > 0).length} areas.
        </div>
      )}
    </div>
  );
};

export default TagsIndexView;

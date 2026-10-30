import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { catalogApi } from "@/lib/api/catalog";
import { chipColors, hueFromSlug } from "@/lib/colors";
import { displayTaskName } from "@/lib/transform";
import { slugify } from "@/lib/slug";
import { taskIcon } from "@/lib/taskIcons";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AreaDirectoryFooter, AreaDirectorySkeleton, AreaSection } from "@/components/AreaSection";
import { TaxonomySuggestionTile } from "@/components/TaxonomySuggestionTile";
import { TrendingTaxonomyGrid } from "@/components/TaxonomyTrending";
import { useHashScrollOnReady } from "@/hooks/useHashScrollOnReady";
import { sortAreas } from "@/lib/areas";
import { catalogQueryKeys, TEN_MINUTES } from "@/lib/api/queryKeys";

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
    staleTime: TEN_MINUTES,
  });
  const trendingQ = useQuery({
    queryKey: ["trending-tasks-directory"],
    queryFn: () => catalogApi.trendingTasks({ limit: 12, min_recent_papers: 10 }),
    staleTime: TEN_MINUTES,
  });
  const areasQ = useQuery({
    queryKey: catalogQueryKeys.areas,
    queryFn: () => catalogApi.listAreas({ page_size: 50, ordering: "name" }),
    staleTime: TEN_MINUTES,
  });

  const trendingItems = useMemo(() => {
    const areaNames = new Map((areasQ.data?.results ?? []).map((area) => [area.id, area.name]));
    const taskSlugs = new Map(
      (taxonomyQ.data?.results ?? []).flatMap((area) => area.tasks.map((task) => [task.id, task.slug])),
    );
    return trendingQ.data?.results.map((task) => ({
      id: task.id,
      name: displayTaskName(task.name, task.slug),
      href: `/tasks/${task.slug}`,
      icon: taskIcon(task.slug ?? "", task.parent_id ? taskSlugs.get(task.parent_id) : undefined),
      iconColor: chipColors(hueFromSlug(task.slug ?? "")).dot,
      areaName: task.area_id ? areaNames.get(task.area_id) : undefined,
      recentPaperCount: task.recent_paper_count,
      shareLift: task.share_lift,
    }));
  }, [trendingQ.data, areasQ.data, taxonomyQ.data]);

  const visibleAreas = useMemo(() => sortAreas(taxonomyQ.data?.results ?? []), [taxonomyQ.data]);

  // Area links (`/tasks#area-…`) target sections that exist only once the
  // taxonomy arrives and sit below the trending section.
  useHashScrollOnReady(!!taxonomyQ.data && !trendingQ.isLoading);

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

      <TrendingTaxonomyGrid
        noun="task"
        items={trendingItems}
        recentDays={trendingQ.data?.recent_days}
        baselineDays={trendingQ.data?.baseline_days}
        isLoading={trendingQ.isLoading}
        error={trendingQ.error}
      />

      {taxonomyQ.isLoading ? (
        <AreaDirectorySkeleton tiles={6} tileClassName="h-24" />
      ) : (
        visibleAreas.map((area) => {
          const tasks = area.tasks;
          if (tasks.length === 0) return null;
          const totalPapers = tasks.reduce((s, t) => s + (t.paper_count || 0), 0);
          return (
            <AreaSection
              key={area.id}
              id={`area-${slugify(area.name)}`}
              title={area.name}
              description={area.description}
              meta={`${tasks.length} ${tasks.length === 1 ? "task" : "tasks"} · ${totalPapers.toLocaleString()} papers`}
            >
              {tasks.map((t) => {
                const slug = t.slug || "";
                const c = chipColors(hueFromSlug(slug));
                const Icon = taskIcon(slug);
                return (
                  <Link key={t.id} to={`/tasks/${slug}`} className="tag-cell">
                    <div className="name">
                      <span className="task-icon" style={{ color: c.dot }}>
                        <Icon size={16} strokeWidth={2} aria-hidden="true" />
                      </span>
                      {displayTaskName(t.name, slug)}
                    </div>
                    <div className="meta">
                      <span>{(t.paper_count ?? 0).toLocaleString()} papers</span>
                    </div>
                  </Link>
                );
              })}
              <TaxonomySuggestionTile kind="task" />
            </AreaSection>
          );
        })
      )}

      <AreaDirectoryFooter areas={visibleAreas} />
    </div>
  );
};

export default TagsIndexView;

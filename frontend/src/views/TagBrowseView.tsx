import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Github, Trophy } from "lucide-react";

import { MethodChip, PaperCard } from "@/components";
import BenchmarkTrendSparkline from "@/components/BenchmarkTrendSparkline";
import MarkdownText from "@/components/MarkdownText";
import { apiClient } from "@/lib/api";
import type { Dataset, Task, TrendingBenchmark } from "@/lib/api";
import { assetUrl } from "@/lib/apiUrl";
import { usePreferences } from "@/lib/preferencesContext";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { useInfiniteTaskPapers } from "@/hooks/usePapers";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

type OrderBy = "trending" | "date_published" | "citation_count";
const SORT_OPTIONS: Array<[OrderBy, string]> = [
  ["trending", "trending"],
  ["date_published", "newest"],
  ["citation_count", "most cited"],
];

const parseOrderBy = (value: string | null): OrderBy => {
  if (value === "trending" || value === "date_published" || value === "citation_count") {
    return value;
  }
  return "trending";
};

const SUBTASK_BENCH_PREVIEW = 3;

const formatStarCount = (stars: number) =>
  new Intl.NumberFormat("en", {
    notation: stars >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(stars);

const sortSubtasksForDisplay = (subtasks: Task[]) =>
  [...subtasks].sort((a, b) => {
    const aIsClassic = a.slug === "classic-language-modeling";
    const bIsClassic = b.slug === "classic-language-modeling";

    if (aIsClassic !== bIsClassic) return aIsClassic ? 1 : -1;
    return 0;
  });

const TagBrowseView: React.FC = () => {
  const { taskSlug } = useParams<{ taskSlug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const orderBy = parseOrderBy(searchParams.get("order_by"));
  const setOrderBy = (next: OrderBy) => {
    const params = new URLSearchParams(searchParams);
    params.set("order_by", next);
    setSearchParams(params);
  };
  const [benchmarksExpanded, setBenchmarksExpanded] = useState(false);
  const [expandedSubtasks, setExpandedSubtasks] = useState<Set<string>>(() => new Set());
  const { preferences } = usePreferences();

  const benchmarkPath = (datasetSlug: string, taskContext?: string) => {
    const slug = datasetSlug || "";
    if (taskContext) {
      return `/benchmark/${slug}?task=${encodeURIComponent(taskContext)}`;
    }
    return `/benchmark/${slug}`;
  };

  const bestModelIsOpen = preferences.hide_closed_source_evals ? true : undefined;

  // One bundled request for the whole task-page shell: task detail, parent
  // chain, sister tasks, visible children, this task's benchmarks, and a short
  // benchmark preview per child. This replaces the previous fan-out of six+
  // independent task/dataset queries on initial load (see Speed plan §1).
  const pageQ = useQuery({
    queryKey: ["task-page", taskSlug, bestModelIsOpen],
    queryFn: () => apiClient.getTaskPage(taskSlug!, { is_open: bestModelIsOpen }),
    enabled: !!taskSlug,
    staleTime: 10 * 60 * 1000,
  });

  const benchmarkTrendsQ = useQuery({
    queryKey: ["task-benchmark-trends", taskSlug, bestModelIsOpen],
    queryFn: () =>
      apiClient.getTrendingBenchmarks(taskSlug!, {
        limit: 100,
        min_recent_papers: 0,
        is_open: bestModelIsOpen,
      }),
    enabled: !!taskSlug,
    staleTime: 10 * 60 * 1000,
  });

  // Subtasks (child tasks). Classic LM is the historical catch-all, so keep it
  // after the capability-oriented subtasks.
  const visibleSubtasks = useMemo(
    () => sortSubtasksForDisplay(pageQ.data?.children || []),
    [pageQ.data],
  );

  // Map each child task id -> its benchmark preview list, so the per-subtask
  // sections can look up benchmarks by id instead of by array index.
  const subtaskBenchmarksById = useMemo(() => {
    const map = new Map<string, Dataset[]>();
    (pageQ.data?.subtask_benchmarks || []).forEach((entry) => {
      map.set(entry.subtask_id, entry.benchmarks || []);
    });
    return map;
  }, [pageQ.data]);

  const papersQ = useInfiniteTaskPapers({
    taskId: pageQ.data?.task?.id || "",
    page_size: 20,
    order_by: orderBy,
    order_dir: "desc",
    include_resources: true,
    enabled: !!pageQ.data?.task?.id,
  });

  const cards = useMemo(() => {
    const all = papersQ.data?.pages.flatMap((p) => p.results) || [];
    return all.map(transformPaperForCard);
  }, [papersQ.data]);

  // Common methods: derived from the loaded papers' methods array.
  const commonMethods = useMemo(() => {
    const counts: Record<string, { id: string; name: string; slug: string; count: number }> = {};
    papersQ.data?.pages.forEach((page) =>
      page.results.forEach((paper) =>
        (paper.methods || []).forEach((m) => {
          const key = m.slug || m.id;
          if (!counts[key]) counts[key] = { id: m.id, name: m.name, slug: m.slug || "", count: 0 };
          counts[key].count++;
        }),
      ),
    );
    return Object.values(counts).sort((a, b) => b.count - a.count).slice(0, 8);
  }, [papersQ.data]);

  const { targetRef: sentinelRef, isIntersecting } = useIntersectionObserver({ rootMargin: "200px" });
  useEffect(() => {
    if (isIntersecting && papersQ.hasNextPage && !papersQ.isFetchingNextPage) {
      papersQ.fetchNextPage();
    }
  }, [isIntersecting, papersQ.hasNextPage, papersQ.isFetchingNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  if (pageQ.isLoading) {
    return (
      <div className="page">
        <Skeleton className="h-12 w-1/2 mb-4" />
        <Skeleton className="h-6 w-1/3 mb-8" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (pageQ.error || !pageQ.data) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Task not found.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const task = pageQ.data.task;
  const parents = pageQ.data.parents || [];
  const taskName = displayTaskName(task.name, task.slug);
  const sisters = (pageQ.data.sisters || []).filter((s) => s.id !== task.id);
  const recommendedFrameworks = pageQ.data.recommended_frameworks || [];
  const datasets = pageQ.data.benchmarks || [];
  const visibleDatasetIds = new Set(datasets.map((dataset) => dataset.id));
  const visibleTrendRows = (benchmarkTrendsQ.data?.results || []).filter((benchmark) =>
    visibleDatasetIds.has(benchmark.id),
  );
  const benchmarkRows: TrendingBenchmark[] =
    visibleTrendRows.length
      ? visibleTrendRows
      : datasets.map((dataset) => ({
          id: dataset.id,
          name: dataset.name,
          slug: dataset.slug,
          full_name: dataset.full_name,
          featured_rank: dataset.featured_rank,
          recent_paper_count: 0,
          baseline_paper_count: 0,
          all_time_paper_count: dataset.paper_count || 0,
          trend_score: 0,
          rate_change: null,
          latest_reported_on: null,
          best_model_name: dataset.best_model_name,
          history: [],
        }));
  const trendWindowDays = benchmarkTrendsQ.data?.recent_days || 90;
  const hasVisibleSubtaskBenchmarks = visibleSubtasks.some(
    (s) => (subtaskBenchmarksById.get(s.id) || []).length > 0,
  );
  const shouldShowSubtaskList = visibleSubtasks.length > 0;
  const shouldShowBenchmarkList = benchmarkRows.length > 0;

  // Total unique benchmarks for the BENCHMARKS quickstat: direct task
  // benchmarks plus visible subtask benchmarks, deduped by dataset id so a
  // benchmark linked to both the parent and a subtask only counts once.
  const totalBenchmarkCount = (() => {
    const ids = new Set<string>();
    datasets.forEach((d) => ids.add(d.id));
    subtaskBenchmarksById.forEach((list) =>
      list.forEach((d) => ids.add(d.id)),
    );
    return ids.size;
  })();

  const toggleSubtaskExpanded = (subtaskId: string) => {
    setExpandedSubtasks((prev) => {
      const next = new Set(prev);
      if (next.has(subtaskId)) next.delete(subtaskId);
      else next.add(subtaskId);
      return next;
    });
  };

  return (
    <div className="page">
      <div className="breadcrumb">
        <Link to="/">Papers</Link>
        <span className="sep">/</span>
        <Link to="/tasks">Tasks</Link>
        {[...parents].reverse().map((parent) => (
          <React.Fragment key={parent.id}>
            <span className="sep">/</span>
            <Link to={`/tasks/${parent.slug || parent.id}`}>
              {displayTaskName(parent.name, parent.slug)}
            </Link>
          </React.Fragment>
        ))}
        <span className="sep">/</span>
        <span style={{ color: "var(--accent-text)" }}>{task.name.toUpperCase()}</span>
      </div>

      <div className={task.image_url ? "task-hero-grid" : undefined}>
        <div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--accent-text)", letterSpacing: "0.1em", marginBottom: 8 }}>
            TASK
          </div>
          <h1 className="domain-mega-title">{taskName}</h1>
          {task.description && (
            <MarkdownText className="task-explainer" text={task.description} />
          )}
          {task.research_trends && task.research_trends.length > 0 && (
            <Accordion className="task-research-trends" type="single" collapsible>
              <AccordionItem className="task-research-trends-item" value="key-trends">
                <AccordionTrigger className="task-research-trends-trigger">
                  <span className="task-research-trends-title">Key trends</span>
                </AccordionTrigger>
                <AccordionContent className="task-research-trends-content">
                  <ul>
                    {task.research_trends.map((trend, index) => (
                      <li key={index}>
                        <MarkdownText text={trend} />
                      </li>
                    ))}
                  </ul>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          )}
          <div className="task-quickstats">
            <span>
              <span className="num">{(task.paper_count ?? 0).toLocaleString()}</span>PAPERS
            </span>
            <span>
              <span className="num">{totalBenchmarkCount}</span>BENCHMARKS
            </span>
            <span>
              <span className="num">{commonMethods.length}+</span>METHODS USED
            </span>
          </div>
          {recommendedFrameworks.length > 0 && (
            <div className="task-framework-links">
              <span className="task-framework-links-label">Recommended frameworks</span>
              {recommendedFrameworks.map((framework) => {
                const label = framework.owner && framework.name
                  ? `${framework.owner}/${framework.name}`
                  : framework.name || framework.url.replace(/^https?:\/\/github\.com\//, "");
                return (
                  <a
                    key={framework.id}
                    href={framework.url}
                    className="task-framework-link"
                    target="_blank"
                    rel="noreferrer"
                  >
                    <Github size={13} strokeWidth={1.8} aria-hidden="true" />
                    <span>{label}</span>
                    <span className="task-framework-link-stars">
                      ★ {formatStarCount(framework.num_stars)}
                    </span>
                  </a>
                );
              })}
            </div>
          )}
        </div>
        {task.image_url && (
          <figure
            className={`task-figure-card${
              task.slug === "omni-models" ? " task-figure-card--compact" : ""
            }`}
          >
            <div className="task-figure-img-wrap">
              <img
                className="task-figure-img"
                src={assetUrl(task.image_url) ?? undefined}
                alt={`${taskName} schematic`}
                onError={(e) => {
                  (e.currentTarget.parentElement?.parentElement as HTMLElement | null)?.style.setProperty("display", "none");
                }}
              />
            </div>
            <figcaption>
              Figure · {taskName}
              {task.image_credit && (
                <>
                  <br />
                  <MarkdownText className="task-image-credit" text={task.image_credit} />
                </>
              )}
            </figcaption>
          </figure>
        )}
      </div>

      <div className="task-page-grid" style={{ marginTop: 28 }}>
        <div>
          {shouldShowBenchmarkList && (
            <>
              <div className="task-section-head">
                <div className="task-section-eyebrow">
                  {trendWindowDays}-day reporting activity · click any
                </div>
                <div className="task-section-title">
                  Benchmarks <span className="meta">[{benchmarkRows.length}]</span>
                </div>
              </div>
              <div className="benchmark-trend-table" role="table" aria-label="Trending benchmarks">
                <div className="benchmark-trend-head" role="row">
                  <span role="columnheader">Trend</span>
                  <span role="columnheader">Benchmark</span>
                  <span role="columnheader">Best model</span>
                  <span aria-hidden="true" />
                </div>
                {(benchmarksExpanded ? benchmarkRows : benchmarkRows.slice(0, 5)).map((benchmark) => (
                  <Link
                    key={benchmark.id}
                    className="benchmark-trend-row"
                    to={benchmarkPath(benchmark.slug || benchmark.id, taskSlug)}
                    role="row"
                  >
                    <div className="benchmark-trend-cell" role="cell">
                      <BenchmarkTrendSparkline
                        history={benchmark.history}
                        benchmarkName={benchmark.name}
                      />
                      <div className="benchmark-trend-meta">
                        <span>
                          <strong>{benchmark.recent_paper_count}</strong>{" "}
                          {benchmark.recent_paper_count === 1 ? "paper" : "papers"} /{" "}
                          {trendWindowDays}d
                        </span>
                        {benchmark.rate_change == null ? (
                          benchmark.recent_paper_count > 0 && (
                            <span className="benchmark-trend-change is-new">new</span>
                          )
                        ) : (
                          <span
                            className={`benchmark-trend-change ${
                              benchmark.rate_change >= 1 ? "is-up" : "is-down"
                            }`}
                          >
                            {benchmark.rate_change >= 1 ? "↑" : "↓"}{" "}
                            {benchmark.rate_change.toFixed(1)}×
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="benchmark-trend-benchmark" role="cell">
                      <div className="bench-row-name">{benchmark.name}</div>
                      <div className="bench-row-sub">
                        <span>
                          <strong>{benchmark.all_time_paper_count}</strong> reporting papers
                        </span>
                      </div>
                    </div>
                    <div className="bench-row-best" role="cell">
                      {benchmark.best_model_name ? (
                        <>
                          <Trophy size={13} className="bench-row-best-icon" />
                          <span className="bench-row-best-name">
                            {benchmark.best_model_name}
                          </span>
                        </>
                      ) : (
                        <span className="bench-row-best-empty">—</span>
                      )}
                    </div>
                    <div className="bench-row-arrow" aria-hidden="true">→</div>
                  </Link>
                ))}
              </div>
              {benchmarkRows.length > 5 && (
                <button
                  type="button"
                  className="bench-show-more"
                  onClick={() => setBenchmarksExpanded((v) => !v)}
                >
                  {benchmarksExpanded
                    ? "− show top 5"
                    : `+ show ${benchmarkRows.length - 5} more benchmarks`}
                </button>
              )}
            </>
          )}

          {shouldShowSubtaskList && (
            <>
              <div
                className="task-section-head"
                style={shouldShowBenchmarkList ? { marginTop: 36 } : undefined}
              >
                <div className="task-section-eyebrow">
                  {hasVisibleSubtaskBenchmarks ? "Benchmarks by capability" : "Task hierarchy"}
                </div>
                <div className="task-section-title">
                  Subtasks <span className="meta">[{visibleSubtasks.length}]</span>
                </div>
              </div>
              <div className="subtask-grid">
                {visibleSubtasks.map((s) => {
                  const subDatasets = subtaskBenchmarksById.get(s.id) || [];
                  const isExpanded = expandedSubtasks.has(s.id);
                  const visibleDatasets = isExpanded
                    ? subDatasets
                    : subDatasets.slice(0, SUBTASK_BENCH_PREVIEW);
                  const remaining = subDatasets.length - SUBTASK_BENCH_PREVIEW;
                  return (
                    <div key={s.id} className="subtask-section">
                      <div className="subtask-head">
                        <Link to={`/tasks/${s.slug || s.id}`} className="subtask-head-name">
                          {displayTaskName(s.name, s.slug)}
                        </Link>
                        <span className="subtask-head-meta">
                          {subDatasets.length > 0
                            ? `[${subDatasets.length} benchmark${subDatasets.length === 1 ? "" : "s"}]`
                            : `[${(s.paper_count ?? 0).toLocaleString()} papers]`}
                        </span>
                      </div>
                      {visibleDatasets.length > 0 ? (
                        visibleDatasets.map((d, i) => (
                          <div
                            key={d.id}
                            className="bench-row"
                            onClick={() => navigate(benchmarkPath(d.slug || d.id, s.slug || s.id))}
                          >
                            <div className="bench-row-num">{String(i + 1).padStart(2, "0")}</div>
                            <div className="bench-row-main">
                              <div className="bench-row-name">{d.name}</div>
                              <div className="bench-row-sub">
                                {d.paper_count != null && (
                                  <span>
                                    <strong>{d.paper_count}</strong> ENTRIES
                                  </span>
                                )}
                              </div>
                            </div>
                            <div className="bench-row-arrow">→</div>
                          </div>
                        ))
                      ) : (
                        <Link to={`/tasks/${s.slug || s.id}`} className="subtask-summary">
                          <span>{(s.paper_count ?? 0).toLocaleString()} papers</span>
                          {s.description && (
                            <span className="subtask-summary-desc">{s.description}</span>
                          )}
                        </Link>
                      )}
                      {remaining > 0 && (
                        <button
                          type="button"
                          className="bench-show-more"
                          onClick={() => toggleSubtaskExpanded(s.id)}
                        >
                          {isExpanded
                            ? `− show top ${SUBTASK_BENCH_PREVIEW}`
                            : `+ show ${remaining} more benchmark${remaining === 1 ? "" : "s"}`}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}

          <div className="task-section-head" style={{ marginTop: 36 }}>
            <div className="task-section-eyebrow">Top trending · sort below</div>
            <div className="task-section-title">
              Papers <span className="meta">[{(task.paper_count ?? 0).toLocaleString()}]</span>
            </div>
          </div>

          <div className="sort-bar">
            <div className="sort-options">
              {SORT_OPTIONS.map(([k, l]) => (
                <button
                  key={k}
                  className={`sort-btn ${orderBy === k ? "active" : ""}`}
                  onClick={() => setOrderBy(k)}
                >
                  {l}
                </button>
              ))}
            </div>
            <div className="results-count">
              {cards.length} loaded in <span>{taskName}</span>
            </div>
          </div>

          {papersQ.isLoading ? (
            <div className="paper-list">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-40 w-full" />
              ))}
            </div>
          ) : cards.length === 0 ? (
            <div className="no-results">No papers in this task yet.</div>
          ) : (
            <>
              <div className="paper-list">
                {cards.map((p, i) => (
                  <PaperCard key={p.id} paper={p} rank={i + 1} />
                ))}
              </div>
              <div ref={sentinelRef} style={{ height: 1 }} />
              {papersQ.isFetchingNextPage && (
                <div style={{ padding: "20px 0", textAlign: "center", color: "var(--ink-faint)" }}>Loading more…</div>
              )}
            </>
          )}
        </div>

        <aside className="task-side">
          {sisters.length > 0 && (
            <div className="side-block">
              <div className="side-block-num">01/</div>
              <div className="side-block-label">Sister Tasks</div>
              {sisters.slice(0, 8).map((s) => (
                <Link key={s.id} to={`/tasks/${s.slug || s.id}`} className="side-link-row">
                  <span>{displayTaskName(s.name, s.slug)}</span>
                  {s.paper_count != null && <span className="count">{s.paper_count.toLocaleString()}</span>}
                </Link>
              ))}
            </div>
          )}

          {commonMethods.length > 0 && (
            <div className="side-block">
              <div className="side-block-num">02/</div>
              <div className="side-block-label">Common Methods</div>
              {commonMethods.map((m) => (
                <div key={m.id} className="side-method-row">
                  <MethodChip method={{ slug: m.slug, name: m.name }} />
                  <span className="num">·{m.count}</span>
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
};

export default TagBrowseView;

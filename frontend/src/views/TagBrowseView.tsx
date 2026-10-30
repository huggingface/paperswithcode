import ResearchFollowButton from "@/components/ResearchFollowButton";
import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Github, Trophy } from "lucide-react";

import { MethodChip } from "@/components/Chips";
import { PaperFeedList, PaperFeedToolbar } from "@/components/PaperFeed";
import { AstraRoboticsFeature } from "@/components/AstraRoboticsFeature";
import BenchmarkTrendSparkline from "@/components/BenchmarkTrendSparkline";
import { groupBenchmarkVariants, variantLabel } from "@/lib/benchmarkVariants";
import MarkdownText from "@/components/MarkdownText";
import type {
  Area,
  Dataset,
  RecommendedFramework,
  Task,
  TrendingBenchmark,
} from "@/lib/api/catalog.types";
import { catalogApi } from "@/lib/api/catalog";
import { papersApi } from "@/lib/api/papers";
import { isNotFound } from "@/lib/apiErrors";
import { assetUrl } from "@/lib/apiUrl";
import { formatStarCount } from "@/lib/frameworks";
import { paperQueryKeys } from "@/lib/paperQueryKeys";
import { usePreferences } from "@/lib/preferences";
import { slugify } from "@/lib/slug";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { usePaperFeedParams } from "@/hooks/usePaperFeedParams";
import { usePaperFeedQuery } from "@/hooks/usePapers";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import NotFound from "@/pages/NotFound";
import { catalogQueryKeys, TEN_MINUTES } from "@/lib/api/queryKeys";

const SUBTASK_BENCH_PREVIEW = 3;

const HEALTHCARE_HUB_DESTINATIONS = [
  {
    slug: "healthcare",
    eyebrow: "Clinical systems",
    title: "Clinical AI & Healthcare",
    description: "Agents, clinical workflows, medical calculators, safety, and decision support.",
    href: "#benchmarks",
  },
  {
    slug: "medical-question-answering",
    eyebrow: "Language & reasoning",
    title: "Medical Question Answering",
    description: "Medical exams, biomedical evidence, clinical comprehension, and explanations.",
    href: "/tasks/medical-question-answering",
  },
  {
    slug: "medical-imaging",
    eyebrow: "Vision",
    title: "Medical Imaging",
    description: "Radiology, pathology, ophthalmology, ultrasound, and diagnostic imaging.",
    href: "/tasks/medical-imaging",
  },
  {
    slug: "medical-visual-question-answering",
    eyebrow: "Multimodal",
    title: "Medical Visual Question Answering",
    description: "Questions grounded in radiology, pathology, and other biomedical images.",
    href: "/tasks/medical-visual-question-answering",
  },
] as const;

export const RecommendedFrameworkLinks: React.FC<{
  frameworks: RecommendedFramework[];
}> = ({ frameworks }) => {
  if (frameworks.length === 0) return null;

  return (
    <div className="task-framework-links">
      <span className="task-framework-links-label">Recommended frameworks</span>
      {frameworks.map((framework) => (
        <Link
          key={framework.framework_id}
          to={`/papers?framework=${encodeURIComponent(framework.framework_slug)}`}
          className="task-framework-link"
        >
          <span>{framework.framework_name}</span>
          <span className="task-framework-link-stars">
            ★ {formatStarCount(framework.num_stars)}
          </span>
        </Link>
      ))}
    </div>
  );
};

export const TaskBreadcrumb: React.FC<{
  task: Task;
  area?: Area;
  parents: Task[];
}> = ({ task, area, parents }) => (
  <nav className="breadcrumb" aria-label="Breadcrumb">
    <Link to="/tasks">Tasks</Link>
    {area && (
      <>
        <span className="sep">/</span>
        <Link to={`/tasks#area-${slugify(area.name)}`}>{area.name}</Link>
      </>
    )}
    {[...parents].reverse().map((parent) => (
      <React.Fragment key={parent.id}>
        <span className="sep">/</span>
        <Link to={`/tasks/${parent.slug || parent.id}`}>
          {displayTaskName(parent.name, parent.slug)}
        </Link>
      </React.Fragment>
    ))}
    <span className="sep">/</span>
    <span style={{ color: "var(--accent-text)" }}>
      {displayTaskName(task.name, task.slug)}
    </span>
  </nav>
);

export const HealthcareMedicalAiHub: React.FC<{
  task: Task;
  relatedTasks: Task[];
}> = ({ task, relatedTasks }) => {
  const tasksBySlug = new Map(
    [task, ...relatedTasks].map((candidate) => [candidate.slug, candidate]),
  );

  return (
    <section className="medical-ai-hub" aria-labelledby="medical-ai-hub-title">
      <div className="medical-ai-hub-heading">
        <span>Medical AI directory</span>
        <h2 id="medical-ai-hub-title">Explore Healthcare &amp; Medical AI</h2>
        <p>Browse the field by clinical application, language, vision, or multimodal reasoning.</p>
      </div>
      <div className="medical-ai-hub-grid">
        {HEALTHCARE_HUB_DESTINATIONS.map((destination) => {
          const destinationTask = tasksBySlug.get(destination.slug);
          const cardContent = (
            <>
              <span className="medical-ai-hub-card-eyebrow">{destination.eyebrow}</span>
              <strong>{destination.title}</strong>
              <span className="medical-ai-hub-card-description">{destination.description}</span>
              <span className="medical-ai-hub-card-meta">
                {destinationTask?.paper_count != null
                  ? `${destinationTask.paper_count.toLocaleString()} papers`
                  : "Explore task"}
                <ArrowRight size={14} aria-hidden="true" />
              </span>
            </>
          );
          return destination.slug === "healthcare" ? (
            <a
              key={destination.slug}
              href={destination.href}
              className="medical-ai-hub-card"
            >
              {cardContent}
            </a>
          ) : (
            <Link
              key={destination.slug}
              to={destination.href}
              className="medical-ai-hub-card"
            >
              {cardContent}
            </Link>
          );
        })}
      </div>
    </section>
  );
};

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
  const feed = usePaperFeedParams();
  const { searchParams } = feed;
  const [benchmarksExpanded, setBenchmarksExpanded] = useState(false);
  // Selected protocol tab per benchmark group, keyed by the group's root id.
  const [selectedVariants, setSelectedVariants] = useState<Record<string, string>>({});
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
    queryKey: [...catalogQueryKeys.taskPage, taskSlug, bestModelIsOpen],
    queryFn: () => catalogApi.taskPage(taskSlug!, { is_open: bestModelIsOpen }),
    enabled: !!taskSlug,
    staleTime: TEN_MINUTES,
  });

  useEffect(() => {
    const canonicalSlug = pageQ.data?.task.slug;
    if (!taskSlug || !canonicalSlug || canonicalSlug === taskSlug) return;

    const query = searchParams.toString();
    navigate(`/tasks/${canonicalSlug}${query ? `?${query}` : ""}`, { replace: true });
  }, [navigate, pageQ.data?.task.slug, searchParams, taskSlug]);

  const benchmarkTrendsQ = useQuery({
    queryKey: [...catalogQueryKeys.taskBenchmarkTrends, taskSlug, bestModelIsOpen],
    queryFn: () =>
      catalogApi.trendingBenchmarks(taskSlug!, {
        limit: 100,
        min_recent_papers: 0,
        is_open: bestModelIsOpen,
      }),
    enabled: !!taskSlug,
    staleTime: TEN_MINUTES,
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

  // The papers endpoint resolves slugs itself, so start the feed in parallel
  // with the task-page shell instead of waiting for its task id.
  const papersQ = usePaperFeedQuery(
    [...paperQueryKeys.feeds.task, taskSlug, feed.filters],
    // Cards show only the leading repository; highly cited papers can
    // otherwise carry hundreds of community implementations each.
    (page) => papersApi.forTask(taskSlug!, { ...feed.filters, page, page_size: 20, repository_limit: 1 }),
    { enabled: !!taskSlug },
  );

  const cards = useMemo(
    () => papersQ.data?.pages.flatMap((page) => page.results.map(transformPaperForCard)) ?? [],
    [papersQ.data],
  );

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

  if (pageQ.isLoading) {
    return (
      <div className="page">
        <Skeleton className="h-12 w-1/2 mb-4" />
        <Skeleton className="h-6 w-1/3 mb-8" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isNotFound(pageQ.error)) return <NotFound />;
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
  const datasetsById = new Map(datasets.map((dataset) => [dataset.id, dataset]));
  const visibleDatasetIds = new Set(datasets.map((dataset) => dataset.id));
  const visibleTrendRows = (benchmarkTrendsQ.data?.results || [])
    .filter((benchmark) => visibleDatasetIds.has(benchmark.id))
    .map((benchmark) => {
      const dataset = datasetsById.get(benchmark.id);
      return {
        ...benchmark,
        best_model_name: dataset?.best_model_name ?? benchmark.best_model_name,
        best_paper_route: dataset?.best_paper_route,
        best_paper_title: dataset?.best_paper_title,
        best_code_url: dataset?.best_code_url,
      };
    });
  const benchmarkRows: Array<TrendingBenchmark & Pick<
    Dataset,
    "best_paper_route" | "best_paper_title" | "best_code_url"
  >> =
    visibleTrendRows.length
      ? visibleTrendRows
      : datasets.map((dataset) => ({
          id: dataset.id,
          name: dataset.name,
          slug: dataset.slug,
          full_name: dataset.full_name,
          recent_paper_count: 0,
          baseline_paper_count: 0,
          all_time_paper_count: dataset.paper_count || 0,
          trend_score: 0,
          support_weighted_score: 0,
          rate_change: null,
          latest_reported_on: null,
          best_model_name: dataset.best_model_name,
          best_paper_route: dataset.best_paper_route,
          best_paper_title: dataset.best_paper_title,
          best_code_url: dataset.best_code_url,
          history: [],
        }));
  const benchmarkGroups = groupBenchmarkVariants(
    benchmarkRows,
    (row) => datasetsById.get(row.id)?.parent_dataset_id,
  );
  const visibleBenchmarkGroups = benchmarksExpanded
    ? benchmarkGroups
    : benchmarkGroups.slice(0, 5);
  const hiddenBenchmarkCount = benchmarkGroups
    .slice(5)
    .reduce((count, group) => count + group.members.length, 0);
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
      <TaskBreadcrumb task={task} area={pageQ.data.area} parents={parents} />

      <div
        className={
          task.image_url
            ? `task-hero-grid${task.slug === "auto-research" ? " task-hero-grid--wide" : ""}`
            : undefined
        }
      >
        <div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--accent-text)", letterSpacing: "0.1em", marginBottom: 8 }}>
            TASK
          </div>
          <h1 className="domain-mega-title">{taskName}</h1>
          <ResearchFollowButton kind="task" entityId={task.id} />
          {task.description && (
            <MarkdownText className="task-explainer" text={task.description} />
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
          <RecommendedFrameworkLinks frameworks={recommendedFrameworks} />
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

      {task.slug === "healthcare" && (
        <HealthcareMedicalAiHub task={task} relatedTasks={sisters} />
      )}

      {task.slug === "robotics" && <AstraRoboticsFeature />}

      <div className="task-page-grid" style={{ marginTop: 28 }}>
        <div>
          {shouldShowBenchmarkList && (
            <>
              <div className="task-section-head" id="benchmarks">
                <div className="task-section-eyebrow">
                  {trendWindowDays}-day reporting activity · select a benchmark
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
                  <span role="columnheader">Paper title</span>
                  <span role="columnheader">Code</span>
                  <span role="columnheader">Compare</span>
                </div>
                {visibleBenchmarkGroups.map(({ key, members: listed }) => {
                  const root = listed[0];
                  const tabLabel = (member: (typeof listed)[number]) =>
                    member === root ? "standard" : variantLabel(member.name, root.name);
                  const members = [
                    root,
                    ...listed
                      .slice(1)
                      .sort((a, b) =>
                        tabLabel(a).localeCompare(tabLabel(b), undefined, { sensitivity: "base" }),
                      ),
                  ];
                  const benchmark =
                    members.find((member) => member.id === selectedVariants[key]) ?? root;
                  return (
                  <div
                    key={key}
                    className="benchmark-trend-row"
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
                      <Link
                        className="bench-row-name"
                        to={benchmarkPath(benchmark.slug || benchmark.id, taskSlug)}
                      >
                        {benchmark.name}
                      </Link>
                      {members.length > 1 && (
                        <div
                          className="bench-row-variants"
                          role="group"
                          aria-label={`Evaluation protocols for ${root.name}`}
                        >
                          {members.map((member) => (
                            <button
                              key={member.id}
                              type="button"
                              className="bench-row-variant"
                              aria-pressed={member.id === benchmark.id}
                              title={member.name}
                              onClick={() =>
                                setSelectedVariants((prev) => ({ ...prev, [key]: member.id }))
                              }
                            >
                              {tabLabel(member)}
                            </button>
                          ))}
                        </div>
                      )}
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
                    <div className="bench-row-paper" role="cell">
                      {benchmark.best_paper_route && benchmark.best_paper_title ? (
                        <Link to={`/paper/${encodeURIComponent(benchmark.best_paper_route)}`}>
                          {benchmark.best_paper_title}
                        </Link>
                      ) : (
                        <span className="bench-row-best-empty">—</span>
                      )}
                    </div>
                    <div className="bench-row-code" role="cell">
                      {benchmark.best_code_url ? (
                        <a
                          href={benchmark.best_code_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label={`Code for ${benchmark.best_paper_title || benchmark.best_model_name}`}
                        >
                          <Github size={18} strokeWidth={1.8} aria-hidden="true" />
                        </a>
                      ) : (
                        <span className="bench-row-best-empty">—</span>
                      )}
                    </div>
                    <div className="bench-row-compare" role="cell">
                      <Link
                        to={benchmarkPath(benchmark.slug || benchmark.id, taskSlug)}
                        aria-label={`Compare ${benchmark.best_model_name || "the best model"} with all results on ${benchmark.name}`}
                      >
                        <span>See all</span>
                        <ArrowRight size={11} strokeWidth={2} aria-hidden="true" />
                      </Link>
                    </div>
                  </div>
                  );
                })}
              </div>
              {benchmarkGroups.length > 5 && (
                <button
                  type="button"
                  className="bench-show-more"
                  onClick={() => setBenchmarksExpanded((v) => !v)}
                >
                  {benchmarksExpanded
                    ? "− show top 5"
                    : `+ show ${hiddenBenchmarkCount} more benchmarks`}
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

          <PaperFeedToolbar feed={feed} />

          <PaperFeedList query={papersQ} cards={cards} empty="No papers in this task yet." />
        </div>

        <aside className="task-side">
          {sisters.length > 0 && task.slug !== "healthcare" && (
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

import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Icon, PaperCard, TagChip } from "@/components";
import { catalogApi } from "@/lib/api/catalog";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { useInfinitePapers, useInfinitePaperSearch } from "@/hooks/usePapers";
import { useDebounce } from "@/hooks/useDebounce";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useQuery } from "@tanstack/react-query";
import { PaperFeedFilters } from "@/components/PaperFeedFilters";
import { PaperDateFilter } from "@/components/PaperDateFilter";
import { ApiError } from "@/lib/apiTransport";
import { readPaperDateRange, withPaperDateRange } from "@/lib/paperDateRange";
import { queryCenteredExcerpt } from "@/lib/paperSearchPresentation";
import { isChatEnabled } from "@/lib/apiUrl";

type SortKey = "trending" | "relevance" | "new" | "cited";
const ALL_PAPERS_SORT_OPTIONS: Array<[SortKey, string]> = [
  ["trending", "trending"],
  ["new", "newest"],
  ["cited", "most cited"],
];
const SEARCH_SORT_OPTIONS: Array<[SortKey, string]> = [
  ["relevance", "relevance"],
  ["new", "newest"],
  ["cited", "most cited"],
];

const formatStarCount = (stars: number) =>
  new Intl.NumberFormat("en", {
    notation: stars >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(stars);

const PapersListView: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const framework = searchParams.get("framework") || undefined;
  const repository = searchParams.get("repository") || undefined;
  const isRepositoryFeed = Boolean(framework || repository);
  const urlSearch = searchParams.get("search") || "";
  const [searchInput, setSearchInput] = useState(urlSearch);
  const debouncedSearch = useDebounce(searchInput, 300);
  const isSearchMode = !isRepositoryFeed && urlSearch.trim().length > 0;

  useEffect(() => setSearchInput(urlSearch), [urlSearch]);

  // Mirror debounced text into the URL so the search is bookmarkable.
  useEffect(() => {
    if (debouncedSearch === urlSearch) return;
    const next = new URLSearchParams(searchParams);
    if (debouncedSearch) next.set("search", debouncedSearch);
    else next.delete("search");
    setSearchParams(next, { replace: true });
  }, [debouncedSearch]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const requested = searchParams.get("order_by");
    const next = new URLSearchParams(searchParams);
    if (isSearchMode && !["relevance", "date_published", "citation_count"].includes(requested || "")) {
      next.set("order_by", "relevance");
      setSearchParams(next, { replace: true });
    } else if (!isSearchMode && requested === "relevance") {
      next.delete("order_by");
      setSearchParams(next, { replace: true });
    }
  }, [isSearchMode, searchParams, setSearchParams]);

  const requestedOrder = searchParams.get("order_by");
  const sortBy: SortKey = requestedOrder === "citation_count"
    ? "cited"
    : requestedOrder === "date_published"
      ? "new"
      : isSearchMode
        ? "relevance"
        : "trending";
  const dateRange = readPaperDateRange(searchParams);
  const hasHfArtifacts = searchParams.get("has_hf_artifacts") === "true";
  const hasCode = !isRepositoryFeed && searchParams.get("has_code") === "true";

  const setQueryParam = (key: string, value?: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
  };

  const setSortBy = (nextSort: SortKey) => {
    setQueryParam(
      "order_by",
      nextSort === "cited" ? "citation_count" : nextSort === "new" ? "date_published" : nextSort,
    );
  };

  const orderBy =
    sortBy === "trending"
      ? "trending"
      : sortBy === "cited"
        ? "citation_count"
        : "date_published";
  const regularInfinite = useInfinitePapers({
    page_size: 20,
    order_by: orderBy,
    order_dir: "desc",
    search: isRepositoryFeed ? debouncedSearch || undefined : undefined,
    start_date: dateRange.startDate,
    end_date: dateRange.endDate,
    include_resources: true,
    conference: searchParams.get("conference") || undefined,
    latest_only: searchParams.get("latest_only") !== "false",
    has_code: hasCode,
    has_hf_artifacts: hasHfArtifacts,
    framework,
    repository,
    enabled: !isSearchMode,
  });

  const searchInfinite = useInfinitePaperSearch({
    q: debouncedSearch.trim(),
    order_by: sortBy === "cited" ? "citation_count" : sortBy === "new" ? "date_published" : "relevance",
    start_date: dateRange.startDate,
    end_date: dateRange.endDate,
    has_code: hasCode,
    has_hf_artifacts: hasHfArtifacts,
    enabled: isSearchMode,
  });
  const infinite = isSearchMode ? searchInfinite : regularInfinite;

  const topTasks = useQuery({
    queryKey: ["top-tasks-sidebar"],
    queryFn: () => catalogApi.topTasks(8),
    enabled: !isRepositoryFeed && !isSearchMode,
    staleTime: 10 * 60 * 1000,
  });

  const cards = useMemo(() => {
    const all = infinite.data?.pages.flatMap((p) => p.results) || [];
    return all.map((paper) => {
      const card = transformPaperForCard(paper);
      return isSearchMode
        ? { ...card, abstract: queryCenteredExcerpt(card.abstract, urlSearch) }
        : card;
    });
  }, [infinite.data, isSearchMode, urlSearch]);

  const { targetRef: sentinelRef, isIntersecting } = useIntersectionObserver({ rootMargin: "200px" });
  useEffect(() => {
    if (isIntersecting && infinite.hasNextPage && !infinite.isFetchingNextPage) {
      infinite.fetchNextPage();
    }
  }, [isIntersecting, infinite.hasNextPage, infinite.isFetchingNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  const totalCount = regularInfinite.data?.pages?.[0]?.count ?? 0;
  const scope = regularInfinite.data?.pages?.[0]?.scope;
  const searchMetadata = searchInfinite.data?.pages?.at(-1);
  const frameworkNotFound = framework && infinite.error instanceof ApiError && infinite.error.status === 404;
  const headingName = scope?.kind === "framework" ? scope.framework_name : scope?.repository;

  return (
    <div className="page">
      {scope?.kind === "framework" && (
        <nav className="breadcrumb" aria-label="Breadcrumb">
          <Link to="/">Papers</Link>
          <span className="sep">/</span>
          <Link to="/frameworks">Frameworks</Link>
          <span className="sep">/</span>
          <span style={{ color: "var(--ink)" }}>{scope.framework_name}</span>
        </nav>
      )}
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            {isRepositoryFeed
              ? <>Papers implemented by <em>{headingName || framework || repository}</em></>
              : isSearchMode
                ? <>Search results for <em>“{urlSearch}”</em></>
                : <>All <em>Papers</em></>}
          </h1>
          <div className="feed-subtitle">
            {isRepositoryFeed
              ? scope?.kind === "framework"
                ? totalCount > 0 && `${totalCount.toLocaleString()} papers.`
                : scope?.repository
                ? <>GitHub repository <strong>{scope.repository}</strong>. {totalCount > 0 && `${totalCount.toLocaleString()} papers.`}</>
                : "Repository-scoped paper feed."
              : isSearchMode
                ? `${cards.length} loaded from the most relevant results.`
                : <>Search the full corpus. {totalCount > 0 && `${totalCount.toLocaleString()} papers indexed.`}</>}
          </div>
          {isRepositoryFeed && scope && (
            <div className="paper-feed-scope-links">
              <div className="paper-feed-primary-links">
                {scope.github_url && (
                  <a
                    href={scope.github_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={scope.kind === "framework" ? "task-framework-link" : "framework-link"}
                  >
                    <Icon name="github" size={13} />
                    {scope.kind === "framework" ? (
                      <>
                        <span>{scope.repository || "GitHub"}</span>
                        {scope.num_stars != null && (
                          <span className="task-framework-link-stars">
                            ★ {formatStarCount(scope.num_stars)}
                          </span>
                        )}
                      </>
                    ) : "GitHub"}
                  </a>
                )}
                {scope.kind === "framework" && scope.introducing_paper_arxiv_id && (
                  <Link
                    to={`/paper/${scope.introducing_paper_arxiv_id}`}
                    className="framework-link"
                  >
                    Introducing paper
                  </Link>
                )}
              </div>
              {scope.kind === "framework" && scope.recommended_tasks && scope.recommended_tasks.length > 0 && (
                <div className="paper-feed-task-tags">
                  {scope.recommended_tasks.map((task) =>
                    task.slug ? <TagChip key={task.id} slug={task.slug} label={task.name} /> : null
                  )}
                </div>
              )}
            </div>
          )}
        </div>
        <PaperDateFilter
          startDate={dateRange.startDate}
          endDate={dateRange.endDate}
          onChange={(value) => setSearchParams(withPaperDateRange(searchParams, value))}
        />
      </div>

      <div className="papers-search-row">
        <div className="papers-search-input-wrap">
          <Icon name="search" size={14} />
          <input
            className="papers-search-input"
            placeholder="Search title or abstract…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>
      </div>

      <div className={isRepositoryFeed || isSearchMode ? "papers-feed-layout-scoped" : "layout-with-sidebar"}>
        {!isRepositoryFeed && !isSearchMode && <aside className="sidebar">
          <div className="sidebar-section">
            <div className="sidebar-label">Top Domains</div>
            {topTasks.isLoading && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-5 w-full" />
                ))}
              </div>
            )}
            <div className="sidebar-links">
              {topTasks.data?.map((task) => (
                <Link key={task.id} to={`/tasks/${task.slug}`} className="sidebar-link">
                  {displayTaskName(task.name, task.slug)}
                  {task.paper_count != null && <span className="count">{task.paper_count}</span>}
                </Link>
              ))}
            </div>
          </div>
        </aside>}

        <div>
          <div className="sort-bar">
            <div className="paper-feed-toolbar-controls">
              <div className="sort-options">
                {(isSearchMode ? SEARCH_SORT_OPTIONS : ALL_PAPERS_SORT_OPTIONS).map(([k, l]) => (
                  <button
                    key={k}
                    className={`sort-btn ${sortBy === k ? "active" : ""}`}
                    onClick={() => setSortBy(k)}
                  >
                    {l}
                  </button>
                ))}
              </div>
              <PaperFeedFilters
                hasCode={hasCode}
                hasHfArtifacts={hasHfArtifacts}
                onHasCodeChange={(checked) => setQueryParam("has_code", checked ? "true" : undefined)}
                onHasHfArtifactsChange={(checked) => setQueryParam("has_hf_artifacts", checked ? "true" : undefined)}
                showHasCode={!isRepositoryFeed}
              />
            </div>
            <div className="results-count">{cards.length} loaded</div>
          </div>

          {frameworkNotFound ? (
            <div className="no-results">Framework not found.</div>
          ) : infinite.error && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>Failed to load papers. Please try again.</AlertDescription>
            </Alert>
          )}

          {!frameworkNotFound && (infinite.isLoading ? (
            <div className="paper-list">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="paper-card">
                  <Skeleton className="h-[220px] w-[160px]" />
                  <div className="paper-body" style={{ flex: 1, gap: 12 }}>
                    <Skeleton className="h-6 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                    <Skeleton className="h-12 w-full" />
                  </div>
                </div>
              ))}
            </div>
          ) : cards.length === 0 ? (
            <div className="no-results">
              <p>No matching papers.</p>
              {isSearchMode && isChatEnabled() && (
                <Link to={`/chat?q=${encodeURIComponent(urlSearch.trim())}`}>Ask the assistant instead</Link>
              )}
            </div>
          ) : (
            <>
              <div className="paper-list">
                {cards.map((p, i) => (
                  <PaperCard
                    key={p.id}
                    paper={p}
                    rank={i + 1}
                    highlightQuery={isSearchMode ? urlSearch : undefined}
                  />
                ))}
              </div>
              <div ref={sentinelRef} style={{ height: 1 }} />
              {infinite.isFetchingNextPage && (
                <div style={{ padding: "20px 0", textAlign: "center", color: "var(--ink-faint)" }}>
                  Loading more…
                </div>
              )}
              {!infinite.hasNextPage && !infinite.isFetchingNextPage && isSearchMode && (
                <div className="search-results-end">
                  {searchMetadata?.cap_reached
                    ? "End of the top 100 results"
                    : "End of results"}
                </div>
              )}
            </>
          ))}
        </div>
      </div>
    </div>
  );
};

export default PapersListView;

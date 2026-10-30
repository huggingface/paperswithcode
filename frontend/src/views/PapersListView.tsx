import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { TagChip } from "@/components/Chips";
import { Icon } from "@/components/Icon";
import { PaperFeedList, PaperFeedToolbar } from "@/components/PaperFeed";
import { catalogApi } from "@/lib/api/catalog";
import { papersApi } from "@/lib/api/papers";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { usePaperFeedQuery } from "@/hooks/usePapers";
import { PAPER_FEED_SORTS, usePaperFeedParams } from "@/hooks/usePaperFeedParams";
import { useDebounce } from "@/hooks/useDebounce";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useQuery } from "@tanstack/react-query";
import { PaperDateFilter } from "@/components/PaperDateFilter";
import { isNotFound } from "@/lib/apiErrors";
import { formatStarCount } from "@/lib/frameworks";
import { paperQueryKeys } from "@/lib/paperQueryKeys";
import { queryCenteredExcerpt } from "@/lib/paperSearchPresentation";
import { isChatEnabled } from "@/lib/apiUrl";
import { catalogQueryKeys, TEN_MINUTES } from "@/lib/api/queryKeys";

const SEARCH_SORTS = [
  ["relevance", "relevance"],
  ["date_published", "newest"],
  ["citation_count", "most cited"],
] as const;

const PapersListView: React.FC = () => {
  const feed = usePaperFeedParams();
  const { searchParams, setSearchParams } = feed;
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

  // Search results default to relevance, which other paper feeds do not offer.
  const sortBy = isSearchMode && feed.orderBy === "trending" ? "relevance" : feed.orderBy;
  const hasCode = !isRepositoryFeed && feed.hasCode;

  const listFilters = {
    ...feed.filters,
    has_code: hasCode,
    search: isRepositoryFeed ? debouncedSearch || undefined : undefined,
    conference: searchParams.get("conference") || undefined,
    latest_only: searchParams.get("latest_only") !== "false",
    framework,
    repository,
  };
  const regularInfinite = usePaperFeedQuery(
    [...paperQueryKeys.feeds.infinite, listFilters],
    (page) => papersApi.list({ ...listFilters, page, page_size: 20 }),
    { enabled: !isSearchMode },
  );

  const searchFilters = {
    q: debouncedSearch.trim(),
    order_by: sortBy === "trending" ? ("relevance" as const) : sortBy,
    start_date: feed.dateRange.startDate,
    end_date: feed.dateRange.endDate,
    has_code: hasCode,
    has_hf_artifacts: feed.hasHfArtifacts,
  };
  const searchInfinite = usePaperFeedQuery(
    [...paperQueryKeys.feeds.search, searchFilters],
    (page) => papersApi.searchFeed({ ...searchFilters, page, page_size: 20, mode: "hybrid" }),
    { enabled: isSearchMode && searchFilters.q.length > 0 },
  );
  const infinite = isSearchMode ? searchInfinite : regularInfinite;

  const topTasks = useQuery({
    queryKey: catalogQueryKeys.topTasksSidebar,
    queryFn: () => catalogApi.topTasks(8),
    enabled: !isRepositoryFeed && !isSearchMode,
    staleTime: TEN_MINUTES,
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

  const totalCount = regularInfinite.data?.pages?.[0]?.count ?? 0;
  const scope = regularInfinite.data?.pages?.[0]?.scope;
  const searchMetadata = searchInfinite.data?.pages?.at(-1);
  const frameworkNotFound = framework && isNotFound(infinite.error);
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
          startDate={feed.dateRange.startDate}
          endDate={feed.dateRange.endDate}
          onChange={feed.setDateRange}
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
          <PaperFeedToolbar
            feed={feed}
            sorts={isSearchMode ? SEARCH_SORTS : PAPER_FEED_SORTS}
            activeSort={sortBy}
            showDateFilter={false}
            showHasCode={!isRepositoryFeed}
          >
            <div className="results-count">{cards.length} loaded</div>
          </PaperFeedToolbar>

          {frameworkNotFound ? (
            <div className="no-results">Framework not found.</div>
          ) : (
            <>
              {infinite.error && (
                <Alert variant="destructive" className="mb-4">
                  <AlertDescription>Failed to load papers. Please try again.</AlertDescription>
                </Alert>
              )}
              <PaperFeedList
                query={infinite}
                cards={cards}
                skeleton="card"
                highlightQuery={isSearchMode ? urlSearch : undefined}
                empty={
                  <>
                    <p>No matching papers.</p>
                    {isSearchMode && isChatEnabled() && (
                      <Link to={`/chat?q=${encodeURIComponent(urlSearch.trim())}`}>Ask the assistant instead</Link>
                    )}
                  </>
                }
              >
                {!infinite.hasNextPage && !infinite.isFetchingNextPage && isSearchMode && (
                  <div className="search-results-end">
                    {searchMetadata?.cap_reached
                      ? "End of the top 100 results"
                      : "End of results"}
                  </div>
                )}
              </PaperFeedList>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default PapersListView;

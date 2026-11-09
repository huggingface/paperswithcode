import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { TagChip } from "@/components/Chips";
import { Icon } from "@/components/Icon";
import { PaperFeedList, PaperFeedToolbar } from "@/components/PaperFeed";
import { papersApi } from "@/lib/api/papers";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { usePaperFeedQuery } from "@/hooks/usePapers";
import { PAPER_FEED_SORTS, usePaperFeedParams } from "@/hooks/usePaperFeedParams";
import { useDebounce } from "@/hooks/useDebounce";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useQuery } from "@tanstack/react-query";
import { PaperDateFilter } from "@/components/PaperDateFilter";
import { isNotFound } from "@/lib/apiTransport";
import { formatStarCount } from "@/lib/frameworks";

import { queryCenteredExcerpt } from "@/lib/paperSearchPresentation";
import { isChatEnabled } from "@/lib/apiUrl";
import { catalogQueries, paperFeedKeys } from "@/lib/api/queries";
import type { Paper } from "@/lib/api/papers.types";
import type { PaginatedResponse } from "@/lib/api/shared.types";

const SEARCH_SORTS = [
  ["relevance", "relevance"],
  ["date_published", "newest"],
  ["citation_count", "most cited"],
] as const;

type PaperScope = NonNullable<PaginatedResponse<Paper>["scope"]>;

/**
 * /papers serves three feeds: papers implemented by one framework or GitHub
 * repository (`scoped`), ranked full-text results (`search`), and the
 * browsable corpus (`browse`). A scope wins over a search query.
 */
type PapersListMode = "scoped" | "search" | "browse";

function papersListMode(searchParams: URLSearchParams): PapersListMode {
  if (searchParams.get("framework") || searchParams.get("repository")) return "scoped";
  return (searchParams.get("search") || "").trim() ? "search" : "browse";
}

const PapersListView: React.FC = () => {
  const [searchParams] = useSearchParams();
  const framework = searchParams.get("framework") || undefined;
  const repository = searchParams.get("repository") || undefined;
  const urlSearch = searchParams.get("search") || "";
  const mode = papersListMode(searchParams);
  const isSearchMode = mode === "search";
  // Browsing defaults to the last month like other paper feeds; search results stay all time.
  const feed = usePaperFeedParams({ defaultToLastMonth: !isSearchMode });
  const { setSearchParams } = feed;
  const [searchInput, setSearchInput] = useState(urlSearch);
  const debouncedSearch = useDebounce(searchInput, 300);

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
  const hasCode = mode !== "scoped" && feed.hasCode;

  const listFilters = {
    ...feed.filters,
    has_code: hasCode,
    search: mode === "scoped" ? debouncedSearch || undefined : undefined,
    conference: searchParams.get("conference") || undefined,
    latest_only: searchParams.get("latest_only") !== "false",
    framework,
    repository,
  };
  const regularInfinite = usePaperFeedQuery(
    paperFeedKeys.list(listFilters),
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
    paperFeedKeys.search(searchFilters),
    (page) => papersApi.searchFeed({ ...searchFilters, page, page_size: 20, mode: "hybrid" }),
    { enabled: isSearchMode && searchFilters.q.length > 0 },
  );
  const infinite = isSearchMode ? searchInfinite : regularInfinite;


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
          <PapersListHeading
            mode={mode}
            scope={scope}
            scopeName={framework || repository}
            search={urlSearch}
            totalCount={totalCount}
            loadedCount={cards.length}
            hasDateRange={Boolean(feed.dateRange.startDate || feed.dateRange.endDate)}
          />
          {mode === "scoped" && scope && <ScopeLinks scope={scope} />}
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

      <div className={mode === "browse" ? "layout-with-sidebar" : "papers-feed-layout-scoped"}>
        {mode === "browse" && <TopDomainsSidebar />}

        <div>
          <PaperFeedToolbar
            feed={feed}
            sorts={isSearchMode ? SEARCH_SORTS : PAPER_FEED_SORTS}
            activeSort={sortBy}
            showDateFilter={false}
            showHasCode={mode !== "scoped"}
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

function PapersListHeading({
  mode,
  scope,
  scopeName,
  search,
  totalCount,
  loadedCount,
  hasDateRange,
}: {
  mode: PapersListMode;
  scope: PaperScope | null | undefined;
  scopeName: string | undefined;
  search: string;
  totalCount: number;
  loadedCount: number;
  hasDateRange: boolean;
}) {
  const papers = totalCount > 0 && `${totalCount.toLocaleString()} papers.`;
  switch (mode) {
    case "scoped": {
      const name = scope?.kind === "framework" ? scope.framework_name : scope?.repository;
      return (
        <>
          <h1 className="feed-title">Papers implemented by <em>{name || scopeName}</em></h1>
          <div className="feed-subtitle">
            {scope?.kind === "framework"
              ? papers
              : scope?.repository
                ? <>GitHub repository <strong>{scope.repository}</strong>. {papers}</>
                : "Repository-scoped paper feed."}
          </div>
        </>
      );
    }
    case "search":
      return (
        <>
          <h1 className="feed-title">Search results for <em>“{search}”</em></h1>
          <div className="feed-subtitle">{`${loadedCount} loaded from the most relevant results.`}</div>
        </>
      );
    case "browse":
      return (
        <>
          <h1 className="feed-title">All <em>Papers</em></h1>
          <div className="feed-subtitle">
            Search the full corpus. {totalCount > 0 && `${totalCount.toLocaleString()} ${hasDateRange ? "papers in this date range" : "papers indexed"}.`}
          </div>
        </>
      );
  }
}

/** GitHub, introducing paper and recommended tasks of a framework or repository feed. */
function ScopeLinks({ scope }: { scope: PaperScope }) {
  const isFramework = scope.kind === "framework";
  return (
    <div className="paper-feed-scope-links">
      <div className="paper-feed-primary-links">
        {scope.github_url && (
          <a
            href={scope.github_url}
            target="_blank"
            rel="noopener noreferrer"
            className={isFramework ? "task-framework-link" : "framework-link"}
          >
            <Icon name="github" size={13} />
            {isFramework ? (
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
        {isFramework && scope.introducing_paper_arxiv_id && (
          <Link
            to={`/paper/${scope.introducing_paper_arxiv_id}`}
            className="framework-link"
          >
            Introducing paper
          </Link>
        )}
      </div>
      {isFramework && scope.recommended_tasks && scope.recommended_tasks.length > 0 && (
        <div className="paper-feed-task-tags">
          {scope.recommended_tasks.map((task) =>
            task.slug ? <TagChip key={task.id} slug={task.slug} label={task.name} /> : null
          )}
        </div>
      )}
    </div>
  );
}

function TopDomainsSidebar() {
  const topTasks = useQuery(catalogQueries.topTasks(8));
  return (
    <aside className="sidebar">
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
    </aside>
  );
}

export default PapersListView;

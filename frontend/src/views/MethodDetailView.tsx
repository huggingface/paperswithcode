import ResearchFollowButton from "@/components/ResearchFollowButton";
import { paperQueryKeys } from "@/lib/paperQueryKeys";
import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { MethodChip, PaperCard } from "@/components";
import { MethodFigure } from "@/components/MethodFigure";
import { PaperFeedFilters } from "@/components/PaperFeedFilters";
import { PaperDateFilter } from "@/components/PaperDateFilter";
import MethodUsageChart from "@/components/MethodUsageChart";
import MarkdownText from "@/components/MarkdownText";
import { catalogApi } from "@/lib/api/catalog";
import { papersApi } from "@/lib/api/papers";
import { slugify } from "@/lib/slug";
import { transformPaperForCard } from "@/lib/transform";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { resolveInternalPath } from "@/lib/internalLinks";
import { safeExternalHref } from "@/lib/safeExternalHref";
import { readPaperDateRange, withPaperDateRange } from "@/lib/paperDateRange";

type SortKey = "trending" | "new" | "cited";
const SORT_OPTIONS: Array<[SortKey, string]> = [
  ["trending", "trending"],
  ["new", "newest"],
  ["cited", "most cited"],
];

const MethodDetailView: React.FC = () => {
  const { methodSlug } = useParams<{ methodSlug: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [sortBy, setSortBy] = useState<SortKey>("trending");
  const hasCode = searchParams.get("has_code") === "true";
  const hasHfArtifacts = searchParams.get("has_hf_artifacts") === "true";
  const dateRange = readPaperDateRange(searchParams);
  const setHasCode = (active: boolean) => {
    const params = new URLSearchParams(searchParams);
    if (active) params.set("has_code", "true");
    else params.delete("has_code");
    setSearchParams(params);
  };
  const setHasHfArtifacts = (active: boolean) => {
    const params = new URLSearchParams(searchParams);
    if (active) params.set("has_hf_artifacts", "true");
    else params.delete("has_hf_artifacts");
    setSearchParams(params);
  };

  const methodQ = useQuery({
    queryKey: ["method", methodSlug],
    queryFn: () => catalogApi.getMethod(methodSlug!),
    enabled: !!methodSlug,
    staleTime: 10 * 60 * 1000,
  });

  const areasQ = useQuery({
    queryKey: ["areas-all"],
    queryFn: () => catalogApi.listAreas({ page_size: 50, ordering: "name" }),
    enabled: !!methodQ.data?.area_id,
    staleTime: 10 * 60 * 1000,
  });

  const trendQ = useQuery({
    queryKey: ["method-trend", methodSlug],
    queryFn: () => catalogApi.methodTrend(methodSlug!),
    enabled: !!methodSlug,
    staleTime: 10 * 60 * 1000,
  });

  const orderBy: "trending" | "citation_count" | "date_published" =
    sortBy === "trending" ? "trending" : sortBy === "cited" ? "citation_count" : "date_published";
  const papersQ = useInfiniteQuery({
    queryKey: [
      ...paperQueryKeys.feeds.method,
      methodSlug,
      orderBy,
      hasCode,
      hasHfArtifacts,
      dateRange.startDate,
      dateRange.endDate,
    ],
    queryFn: ({ pageParam = 1 }) =>
      papersApi.forMethod(methodSlug!, {
        page: pageParam as number,
        page_size: 20,
        order_by: orderBy,
        order_dir: "desc",
        include_resources: true,
        // Cards show only the leading repository.
        repository_limit: 1,
        has_code: hasCode,
        has_hf_artifacts: hasHfArtifacts,
        start_date: dateRange.startDate,
        end_date: dateRange.endDate,
      }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled: !!methodSlug,
    staleTime: 5 * 60 * 1000,
    placeholderData: keepPreviousData,
  });

  const relatedQ = useQuery({
    queryKey: ["related-methods", methodSlug],
    queryFn: () => catalogApi.relatedMethods(methodSlug!),
    enabled: !!methodSlug,
    staleTime: 10 * 60 * 1000,
  });

  const cards = useMemo(() => {
    const all = papersQ.data?.pages.flatMap((p) => p.results) || [];
    return all.map(transformPaperForCard);
  }, [papersQ.data]);

  const { targetRef: sentinelRef, isIntersecting } = useIntersectionObserver({ rootMargin: "200px" });
  useEffect(() => {
    if (isIntersecting && papersQ.hasNextPage && !papersQ.isFetchingNextPage) {
      papersQ.fetchNextPage();
    }
  }, [isIntersecting, papersQ.hasNextPage, papersQ.isFetchingNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  if (methodQ.isLoading) {
    return (
      <div className="page">
        <Skeleton className="h-12 w-1/2 mb-4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (methodQ.error || !methodQ.data) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Method not found.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const m = methodQ.data;
  const area = areasQ.data?.results.find((candidate) => candidate.id === m.area_id);
  const internalSourcePath = resolveInternalPath(m.source_url);
  const externalSourceHref = internalSourcePath ? null : safeExternalHref(m.source_url);

  return (
    <div className="page">
      <div className="breadcrumb">
        <Link to="/methods">Methods</Link>
        {area && (
          <>
            <span className="sep">/</span>
            <Link to={`/methods#area-${slugify(area.name)}`}>{area.name}</Link>
          </>
        )}
        <span className="sep">/</span>
        <span style={{ color: "var(--ink)" }}>{m.name}</span>
      </div>

      <div
        className={`tag-hero method-hero-grid${
          m.slug === "grokking" ||
          m.slug === "latent-reasoning" ||
          m.slug === "world-action-models"
            ? " method-hero-grid--wide-figure"
            : ""
        }`}
      >
        <div>
          <div className="tag-hero-eyebrow">METHOD</div>
          <h1 className="tag-hero-title method-hero-title">{m.name}</h1>
          <ResearchFollowButton kind="method" entityId={m.id} />
          {m.full_name && !m.name.includes(m.full_name) && (
            <div style={{ fontFamily: "var(--serif)", fontSize: 16, fontStyle: "italic", color: "var(--ink-soft)", marginTop: 8 }}>
              {m.full_name}
            </div>
          )}
          {m.description && (
            <MarkdownText className="method-description" text={m.description} />
          )}
          {m.source_url && m.source_title && (
            <div className="method-source">
              <span className="method-source-label">Source</span>
              {internalSourcePath ? (
                <Link
                  className="method-source-link"
                  to={internalSourcePath}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <span className="method-source-title">{m.source_title}</span>
                  {m.introduced_year && <span className="method-source-meta">{m.introduced_year}</span>}
                </Link>
              ) : externalSourceHref ? (
                <a
                  className="method-source-link"
                  href={externalSourceHref}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <span className="method-source-title">{m.source_title}</span>
                  {m.introduced_year && <span className="method-source-meta">{m.introduced_year}</span>}
                </a>
              ) : (
                <div className="method-source-link is-static">
                  <span className="method-source-title">{m.source_title}</span>
                  {m.introduced_year && <span className="method-source-meta">{m.introduced_year}</span>}
                </div>
              )}
            </div>
          )}
          <div className="tag-hero-meta">
            <div className="stat">
              <span className="label">Papers mentioning</span>
              <span className="value">{(m.paper_count ?? 0).toLocaleString()}</span>
            </div>
            {trendQ.data && (
              <div className="stat">
                <span className="label">Recent mentions</span>
                <span className="value">
                  {(trendQ.data.recent_paper_count * 30 / trendQ.data.recent_days).toFixed(1)}
                  <small>/mo</small>
                </span>
                {!trendQ.data.comparison_complete && (
                  <span title="Tagging is still catching up. This rate reflects mentions found so far.">
                    Partial coverage
                  </span>
                )}
              </div>
            )}
            {m.introduced_year != null && (
              <div className="stat">
                <span className="label">Introduced</span>
                <span className="value">{m.introduced_year}</span>
              </div>
            )}
          </div>
          {trendQ.isLoading ? (
            <Skeleton className="h-36 w-full method-trend-skeleton" />
          ) : trendQ.data ? (
            <section className="method-trend-panel method-trend-panel--compact">
              <div className="method-trend-header">
                <div>
                  <div className="method-trend-eyebrow">Usage trend</div>
                </div>
                <div className="method-trend-summary">
                  <strong>{trendQ.data.recent_paper_count}</strong>
                  <span>papers / {trendQ.data.recent_days}d</span>
                </div>
              </div>
              <MethodUsageChart
                history={trendQ.data.history}
                methodName={m.name}
              />
            </section>
          ) : null}
        </div>
        <figure className="method-figure-card">
          <MethodFigure method={m} />
          {m.image_credit && (
            <figcaption>
              <MarkdownText className="method-image-credit" text={m.image_credit} />
            </figcaption>
          )}
        </figure>
      </div>

      {(relatedQ.data?.results.length ?? 0) > 0 && (
        <div className="filter-row">
          <span className="label">Related methods</span>
          {relatedQ.data!.results.map((rm) => (
            <MethodChip key={rm.id} method={{ slug: rm.slug, name: rm.name }} />
          ))}
        </div>
      )}

      <div className="sort-bar">
        <div className="paper-feed-toolbar-controls">
          <div className="sort-options">
            {SORT_OPTIONS.map(([k, l]) => (
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
            onHasCodeChange={setHasCode}
            onHasHfArtifactsChange={setHasHfArtifacts}
          />
        </div>
        <PaperDateFilter
          startDate={dateRange.startDate}
          endDate={dateRange.endDate}
          onChange={(value) => setSearchParams(withPaperDateRange(searchParams, value))}
        />
        <div className="results-count">{cards.length} papers mentioning {m.name}</div>
      </div>

      {papersQ.isLoading ? (
        <div className="paper-list">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      ) : cards.length === 0 ? (
        <div className="no-results">No papers tagged with this method yet.</div>
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
  );
};

export default MethodDetailView;

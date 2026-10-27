import React, { useEffect, useMemo } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { PaperCard } from "@/components";
import { AuthorAvatar } from "@/components/AuthorAvatar";
import { PaperDateFilter } from "@/components/PaperDateFilter";
import { PaperFeedFilters } from "@/components/PaperFeedFilters";
import ResearchFollowButton from "@/components/ResearchFollowButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { useInfinitePapers } from "@/hooks/usePapers";
import { papersApi } from "@/lib/api/papers";
import { readPaperDateRange, withPaperDateRange } from "@/lib/paperDateRange";
import { transformPaperForCard } from "@/lib/transform";
import NotFound from "@/pages/NotFound";

type OrderBy = "trending" | "date_published" | "citation_count";
const SORT_OPTIONS: Array<[OrderBy, string]> = [
  ["trending", "trending"],
  ["date_published", "newest"],
  ["citation_count", "most cited"],
];

const parseOrderBy = (value: string | null): OrderBy =>
  value === "date_published" || value === "citation_count" ? value : "trending";

const AuthorFeed: React.FC<{ authorId: string }> = ({ authorId }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const orderBy = parseOrderBy(searchParams.get("order_by"));
  const hasCode = searchParams.get("has_code") === "true";
  const hasHfArtifacts = searchParams.get("has_hf_artifacts") === "true";
  const dateRange = readPaperDateRange(searchParams);
  const author = useQuery({
    queryKey: ["author", authorId],
    queryFn: () => papersApi.getAuthor(authorId),
  });
  const papers = useInfinitePapers({
    author: authorId,
    page_size: 12,
    order_by: orderBy,
    order_dir: "desc",
    include_resources: true,
    has_code: hasCode,
    has_hf_artifacts: hasHfArtifacts,
    start_date: dateRange.startDate,
    end_date: dateRange.endDate,
  });
  const { targetRef, isIntersecting } = useIntersectionObserver({ rootMargin: "200px" });

  const cards = useMemo(
    () => (papers.data?.pages ?? []).flatMap((page) => page.results.map(transformPaperForCard)),
    [papers.data],
  );

  // Also rerun when results change: a filter change can leave the sentinel visible.
  useEffect(() => {
    if (isIntersecting && papers.hasNextPage && !papers.isFetchingNextPage) {
      papers.fetchNextPage();
    }
  }, [isIntersecting, papers.hasNextPage, papers.isFetchingNextPage, cards.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const totalCount = papers.data?.pages[0]?.count ?? 0;

  const setParam = (key: string, value: string | null) => {
    const updated = new URLSearchParams(searchParams);
    if (value) updated.set(key, value);
    else updated.delete(key);
    setSearchParams(updated);
  };

  if ((author.error as { status?: number } | null)?.status === 404) {
    return <NotFound />;
  }
  // arXiv group authors such as "NVIDIA" are organizations, not people.
  if (author.data?.organization_slug) {
    return <Navigate to={`/orgs/${author.data.organization_slug}`} replace />;
  }

  return (
    <div className="page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <span> / </span>
        <span>Authors</span>
        <span> / </span>
        <span>{author.data?.full_name ?? authorId}</span>
      </nav>

      <header className="author-hero">
        <div className="organizations-eyebrow">AUTHOR</div>
        <div className="author-hero-title">
          {author.data?.hf_username && (
            <AuthorAvatar
              className="author-avatar"
              url={author.data.hf_avatar_url}
              href={`https://huggingface.co/${author.data.hf_username}`}
              label={`@${author.data.hf_username} on Hugging Face`}
            />
          )}
          <h1 className="feed-title">
            {author.data?.full_name ?? <Skeleton className="h-12 w-64 inline-block" />}
          </h1>
        </div>
        {author.data && (
          <div className="feed-subtitle">
            {author.data.paper_count.toLocaleString()}{" "}
            {author.data.paper_count === 1 ? "paper" : "papers"}
            {author.data.hf_username && (
              <>
                {" · "}
                <a
                  href={`https://huggingface.co/${author.data.hf_username}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  @{author.data.hf_username} on Hugging Face ↗
                </a>
              </>
            )}
            {author.data.google_scholar_id && (
              <>
                {" · "}
                <a
                  href={`https://scholar.google.com/citations?user=${encodeURIComponent(author.data.google_scholar_id)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Google Scholar ↗
                </a>
              </>
            )}
          </div>
        )}
        {author.data && <ResearchFollowButton kind="author" entityId={author.data.id} />}
      </header>

      <div className="sort-bar" style={{ alignItems: "center", gap: 16 }}>
        <div className="paper-feed-toolbar-controls">
          <div className="sort-options">
            {SORT_OPTIONS.map(([value, label]) => (
              <button
                type="button"
                key={value}
                className={`sort-btn ${orderBy === value ? "active" : ""}`}
                onClick={() => setParam("order_by", value === "trending" ? null : value)}
              >
                {label}
              </button>
            ))}
          </div>
          <PaperFeedFilters
            hasCode={hasCode}
            hasHfArtifacts={hasHfArtifacts}
            onHasCodeChange={(active) => setParam("has_code", active ? "true" : null)}
            onHasHfArtifactsChange={(active) => setParam("has_hf_artifacts", active ? "true" : null)}
          />
        </div>
        <PaperDateFilter
          startDate={dateRange.startDate}
          endDate={dateRange.endDate}
          onChange={(value) => setSearchParams(withPaperDateRange(searchParams, value))}
        />
        <div className="results-count">{totalCount.toLocaleString()} papers</div>
      </div>

      {papers.error ? (
        <Alert variant="destructive">
          <AlertDescription>
            Failed to load papers.{" "}
            <button type="button" onClick={() => void papers.refetch()}>Try again</button>
          </AlertDescription>
        </Alert>
      ) : papers.isLoading ? (
        <div className="paper-list">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-40 w-full" />
          ))}
        </div>
      ) : cards.length === 0 ? (
        <div className="no-results">
          {author.data?.paper_count === 0
            ? "No public papers are available."
            : "No papers found for this selection."}
        </div>
      ) : (
        <>
          <div className="paper-list">
            {cards.map((paper, index) => (
              <PaperCard key={paper.id} paper={paper} rank={index + 1} />
            ))}
          </div>
          <div ref={targetRef} style={{ height: 1 }} />
          {papers.isFetchingNextPage && (
            <div style={{ padding: "20px 0", textAlign: "center" }}>Loading more…</div>
          )}
        </>
      )}
    </div>
  );
};

// Remount per author so the shared feed never shows the previous author's papers.
const AuthorDetailView: React.FC = () => {
  const { authorId } = useParams<{ authorId: string }>();
  return authorId ? <AuthorFeed key={authorId} authorId={authorId} /> : <NotFound />;
};

export default AuthorDetailView;

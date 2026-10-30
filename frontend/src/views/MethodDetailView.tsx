import ResearchFollowButton from "@/components/ResearchFollowButton";
import { paperQueryKeys } from "@/lib/paperQueryKeys";
import React, { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { MethodChip } from "@/components/Chips";
import { MethodFigure } from "@/components/MethodFigure";
import { PaperFeedList, PaperFeedToolbar } from "@/components/PaperFeed";
import MethodUsageChart from "@/components/MethodUsageChart";
import MarkdownText from "@/components/MarkdownText";
import { catalogApi } from "@/lib/api/catalog";
import { papersApi } from "@/lib/api/papers";
import { isNotFound } from "@/lib/apiErrors";
import { slugify } from "@/lib/slug";
import { transformPaperForCard } from "@/lib/transform";
import { usePaperFeedParams } from "@/hooks/usePaperFeedParams";
import { usePaperFeedQuery } from "@/hooks/usePapers";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { resolveInternalPath } from "@/lib/internalLinks";
import { safeExternalHref } from "@/lib/safeExternalHref";
import NotFound from "@/pages/NotFound";
import { catalogQueryKeys, TEN_MINUTES } from "@/lib/api/queryKeys";

const MethodDetailView: React.FC = () => {
  const { methodSlug } = useParams<{ methodSlug: string }>();
  const feed = usePaperFeedParams();

  const methodQ = useQuery({
    queryKey: catalogQueryKeys.method(methodSlug),
    queryFn: () => catalogApi.getMethod(methodSlug!),
    enabled: !!methodSlug,
    staleTime: TEN_MINUTES,
  });

  const areasQ = useQuery({
    queryKey: catalogQueryKeys.areas,
    queryFn: () => catalogApi.listAreas({ page_size: 50, ordering: "name" }),
    enabled: !!methodQ.data?.area_id,
    staleTime: TEN_MINUTES,
  });

  const trendQ = useQuery({
    queryKey: ["method-trend", methodSlug],
    queryFn: () => catalogApi.methodTrend(methodSlug!),
    enabled: !!methodSlug,
    staleTime: TEN_MINUTES,
  });

  const papersQ = usePaperFeedQuery(
    [...paperQueryKeys.feeds.method, methodSlug, feed.filters],
    // Cards show only the leading repository.
    (page) => papersApi.forMethod(methodSlug!, { ...feed.filters, page, page_size: 20, repository_limit: 1 }),
    { enabled: !!methodSlug },
  );

  const relatedQ = useQuery({
    queryKey: ["related-methods", methodSlug],
    queryFn: () => catalogApi.relatedMethods(methodSlug!),
    enabled: !!methodSlug,
    staleTime: TEN_MINUTES,
  });

  const cards = useMemo(
    () => papersQ.data?.pages.flatMap((page) => page.results.map(transformPaperForCard)) ?? [],
    [papersQ.data],
  );

  if (methodQ.isLoading) {
    return (
      <div className="page">
        <Skeleton className="h-12 w-1/2 mb-4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isNotFound(methodQ.error)) return <NotFound />;
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

      <PaperFeedToolbar feed={feed}>
        <div className="results-count">{cards.length} papers mentioning {m.name}</div>
      </PaperFeedToolbar>

      <PaperFeedList query={papersQ} cards={cards} empty="No papers tagged with this method yet." />
    </div>
  );
};

export default MethodDetailView;

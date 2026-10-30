import React from "react";

import { PaperCard } from "@/components/PaperCard";
import { PaperDateFilter } from "@/components/PaperDateFilter";
import { PaperFeedFilters } from "@/components/PaperFeedFilters";
import { Skeleton } from "@/components/ui/skeleton";
import { useInfiniteScroll } from "@/hooks/useInfiniteScroll";
import { PAPER_FEED_SORTS, type PaperFeedParams } from "@/hooks/usePaperFeedParams";
import type { PaperCardProps } from "@/lib/transform";

export const PaperFeedToolbar: React.FC<{
  feed: PaperFeedParams;
  /** Sort buttons as [order_by, label]; null hides them. */
  sorts?: ReadonlyArray<readonly [string, string]> | null;
  activeSort?: string;
  showDateFilter?: boolean;
  showHasCode?: boolean;
  style?: React.CSSProperties;
  leading?: React.ReactNode;
  children?: React.ReactNode;
}> = ({
  feed,
  sorts = PAPER_FEED_SORTS,
  activeSort = feed.orderBy,
  showDateFilter = true,
  showHasCode,
  style,
  leading,
  children,
}) => (
  <div className="sort-bar" style={style}>
    {leading}
    <div className="paper-feed-toolbar-controls">
      {sorts && (
        <div className="sort-options">
          {sorts.map(([value, label]) => (
            <button
              type="button"
              key={value}
              className={`sort-btn ${activeSort === value ? "active" : ""}`}
              onClick={() => feed.setOrderBy(value)}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      <PaperFeedFilters
        hasCode={feed.hasCode}
        hasHfArtifacts={feed.hasHfArtifacts}
        onHasCodeChange={feed.setHasCode}
        onHasHfArtifactsChange={feed.setHasHfArtifacts}
        showDivider={!!sorts}
        showHasCode={showHasCode}
      />
    </div>
    {showDateFilter && (
      <PaperDateFilter
        startDate={feed.dateRange.startDate}
        endDate={feed.dateRange.endDate}
        onChange={feed.setDateRange}
      />
    )}
    {children}
  </div>
);

export type PaperFeedCard = PaperCardProps & { followReasons?: string[] };

const BlockSkeleton = () => <Skeleton className="h-40 w-full" />;

const CardSkeleton = () => (
  <div className="paper-card">
    <div className="paper-thumb-wrap">
      <Skeleton className="paper-thumb-skeleton" />
    </div>
    <div className="paper-body" style={{ flex: 1, gap: 12 }}>
      <Skeleton className="h-6 w-3/4" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-12 w-full" />
    </div>
  </div>
);

/** Paper cards that load the next page as the reader nears the end of the list. */
export const PaperFeedList: React.FC<{
  query: Parameters<typeof useInfiniteScroll>[0] & { isLoading: boolean };
  /** Overrides query.isLoading, e.g. while the feed waits on auth. */
  isLoading?: boolean;
  cards: PaperFeedCard[];
  /** Shown when the feed has no papers; null shows nothing. */
  empty: React.ReactNode;
  /** "card" mirrors the card layout while loading; "block" is a plain placeholder. */
  skeleton?: "block" | "card";
  showInstitution?: boolean;
  highlightQuery?: string;
  /** Optional line rendered above a card, such as an award label. */
  cardHeader?: (index: number) => React.ReactNode;
  rootMargin?: string;
  /** Rendered after the list, e.g. an end-of-results note. */
  children?: React.ReactNode;
}> = ({
  query,
  isLoading = query.isLoading,
  cards,
  empty,
  skeleton = "block",
  showInstitution,
  highlightQuery,
  cardHeader,
  rootMargin,
  children,
}) => {
  const sentinelRef = useInfiniteScroll(query, rootMargin);

  if (isLoading) {
    const Placeholder = skeleton === "card" ? CardSkeleton : BlockSkeleton;
    return (
      <div className="paper-list">
        {Array.from({ length: skeleton === "card" ? 6 : 4 }).map((_, i) => (
          <Placeholder key={i} />
        ))}
      </div>
    );
  }
  if (cards.length === 0) {
    return empty === null ? null : <div className="no-results">{empty}</div>;
  }
  return (
    <>
      <div className="paper-list">
        {cards.map((card, index) => (
          <React.Fragment key={card.id}>
            {cardHeader?.(index)}
            <PaperCard
              paper={card}
              priority={index < 3}
              showInstitution={showInstitution}
              highlightQuery={highlightQuery}
              followReasons={card.followReasons}
            />
          </React.Fragment>
        ))}
      </div>
      <div ref={sentinelRef} style={{ height: 1 }} />
      {query.isFetchingNextPage && (
        <div style={{ padding: "20px 0", textAlign: "center", color: "var(--ink-faint)" }}>
          Loading more…
        </div>
      )}
      {children}
    </>
  );
};

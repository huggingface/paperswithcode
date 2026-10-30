import React, { useEffect, useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { PaperCard } from "@/components";
import { PaperFeedFilters } from "@/components/PaperFeedFilters";
import { PaperDateFilter } from "@/components/PaperDateFilter";
import MarkdownText from "@/components/MarkdownText";
import { catalogApi } from "@/lib/api/catalog";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { useInfiniteConferencePapers } from "@/hooks/usePapers";
import { useInfiniteScroll } from "@/hooks/useInfiniteScroll";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { readPaperDateRange, withPaperDateRange } from "@/lib/paperDateRange";

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

const ConferenceTaskView: React.FC = () => {
  const { confSlug, taskSlug } = useParams<{ confSlug: string; taskSlug: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const orderBy = parseOrderBy(searchParams.get("order_by"));
  const hasCode = searchParams.get("has_code") === "true";
  const hasHfArtifacts = searchParams.get("has_hf_artifacts") === "true";
  const dateRange = readPaperDateRange(searchParams);
  const setOrderBy = (next: OrderBy) => {
    const params = new URLSearchParams(searchParams);
    params.set("order_by", next);
    setSearchParams(params);
  };
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

  const isAllPapers = taskSlug === "all";
  const isOralPapers = taskSlug === "oral";
  const isSpotlightPapers = taskSlug === "spotlight";
  const isOutstandingPapers = taskSlug === "outstanding";
  const isBestPaperFinalists = taskSlug === "best-paper-finalists";
  const isAwardListing = isOutstandingPapers || isBestPaperFinalists;
  const isBrowseListing =
    isAllPapers ||
    isOralPapers ||
    isSpotlightPapers ||
    isOutstandingPapers ||
    isBestPaperFinalists;
  const apiTaskSlug = isBrowseListing ? undefined : taskSlug;
  const apiPresentation = isOralPapers
    ? "oral"
    : isSpotlightPapers
      ? "spotlight"
      : isOutstandingPapers
        ? "outstanding"
        : isBestPaperFinalists
          ? "best_paper_finalist"
          : undefined;

  const conferenceQ = useQuery({
    queryKey: ["conference", confSlug],
    queryFn: () => catalogApi.getConference(confSlug!),
    enabled: !!confSlug,
    staleTime: 10 * 60 * 1000,
  });

  const taskQ = useQuery({
    queryKey: ["task", taskSlug],
    queryFn: () => catalogApi.getTask(taskSlug!),
    enabled: !!taskSlug && !isBrowseListing,
    staleTime: 10 * 60 * 1000,
  });

  const papersQ = useInfiniteConferencePapers({
    conferenceSlug: confSlug || "",
    taskSlug: apiTaskSlug,
    presentation: apiPresentation,
    page_size: 12,
    order_by: orderBy,
    order_dir: "desc",
    include_resources: true,
    has_code: hasCode,
    has_hf_artifacts: hasHfArtifacts,
    start_date: dateRange.startDate,
    end_date: dateRange.endDate,
    enabled: !!confSlug,
  });


  const sentinelRef = useInfiniteScroll(papersQ);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [confSlug, taskSlug]);

  const paperRows = useMemo(() => {
    const pages = papersQ.data?.pages ?? [];
    return pages.flatMap((page) => page.results);
  }, [papersQ.data]);

  const cards = useMemo(
    () => paperRows.map(transformPaperForCard),
    [paperRows],
  );

  const taskName = isAllPapers
    ? "All papers"
    : isOralPapers
      ? "Oral papers"
      : isSpotlightPapers
        ? "Spotlight papers"
        : isOutstandingPapers
          ? "Outstanding papers"
          : isBestPaperFinalists
            ? "Best paper finalists"
            : displayTaskName(taskQ.data?.name || taskSlug || "", taskQ.data?.slug || taskSlug);

  const totalCount = papersQ.data?.pages[0]?.count ?? conferenceQ.data?.paper_count ?? 0;
  const task = taskQ.data;

  if (conferenceQ.error || taskQ.error || papersQ.error) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Failed to load conference papers. Please try again.</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <span> / </span>
        <Link to="/conferences">Conferences</Link>
        <span> / </span>
        <Link to={`/conferences/${confSlug}`}>{conferenceQ.data?.name ?? confSlug}</Link>
        <span> / </span>
        <span>{taskName}</span>
      </nav>

      <div className={!isBrowseListing && task?.image_url ? "task-hero-grid" : undefined} style={{ marginTop: 16, marginBottom: 28 }}>
        <div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--accent-text)", letterSpacing: "0.1em", marginBottom: 8 }}>
            {isBrowseListing ? "BROWSE PAPERS" : "TASK"}
          </div>
          <h1 className="domain-mega-title">{taskName}</h1>
          {isOutstandingPapers && confSlug === "iclr-2026" && (
            <MarkdownText
              className="task-explainer"
              text={
                "ICLR 2026 recognized two Outstanding Papers and one Honorable Mention. " +
                "[Read the announcement](https://blog.iclr.cc/2026/04/23/announcing-the-iclr-2026-outstanding-papers/)."
              }
            />
          )}
          {isOutstandingPapers && confSlug === "icml-2026" && (
            <MarkdownText
              className="task-explainer"
              text={
                "ICML 2026 recognized two Outstanding Papers and five Honorable Mentions. " +
                "[Read the announcement](https://blog.icml.cc/2026/07/05/announcing-the-icml-2026-awards/)."
              }
            />
          )}
          {isBestPaperFinalists && confSlug === "cvpr-2026" && (
            <MarkdownText
              className="task-explainer"
              text={
                "CVPR 2026 recognized fifteen Best Paper Award finalists, including the winners. " +
                "[Read the announcement](https://x.com/CVPR/status/2062912519522717978)."
              }
            />
          )}
          {!isBrowseListing && task?.description && (
            <MarkdownText className="task-explainer" text={task.description} />
          )}
          {conferenceQ.data && (
            <div className="task-quickstats" style={{ marginTop: 12 }}>
              <span>
                <span className="num">{totalCount.toLocaleString()}</span>PAPERS
              </span>
              <span>{conferenceQ.data.name}</span>
            </div>
          )}
        </div>
        {!isBrowseListing && task?.image_url && (
          <figure className="task-figure-card">
            <div className="task-figure-img-wrap">
              <img
                className="task-figure-img"
                src={task.image_url}
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

      <div className="task-section-head">
        <div className="task-section-eyebrow">
          {isAwardListing ? "Award papers" : "Conference papers · sort below"}
        </div>
        <div className="task-section-title">
          Papers <span className="meta">[{totalCount.toLocaleString()}]</span>
        </div>
      </div>

      <div className="sort-bar">
        <div className="paper-feed-toolbar-controls">
          {!isAwardListing && (
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
          )}
          <PaperFeedFilters
            hasCode={hasCode}
            hasHfArtifacts={hasHfArtifacts}
            onHasCodeChange={setHasCode}
            onHasHfArtifactsChange={setHasHfArtifacts}
            showDivider={!isAwardListing}
          />
        </div>
        <PaperDateFilter
          startDate={dateRange.startDate}
          endDate={dateRange.endDate}
          onChange={(value) => setSearchParams(withPaperDateRange(searchParams, value))}
        />
        {!isAwardListing && (
          <div className="results-count">
            {cards.length} loaded in <span>{taskName}</span>
          </div>
        )}
      </div>

      {papersQ.isLoading ? (
        <div className="paper-list">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      ) : cards.length === 0 ? (
        <div className="no-results">No papers found for this selection.</div>
      ) : (
        <>
          <div className="paper-list">
            {cards.map((p, i) => {
              const award = paperRows[i]?.conference_award;
              const awardLabel =
                award === "outstanding"
                  ? "Outstanding Paper"
                  : award === "honorable_mention"
                    ? "Honorable Mention"
                    : award === "best_paper_finalist" && !isBestPaperFinalists
                      ? "Best Paper Finalist"
                      : null;
              return (
                <React.Fragment key={p.id}>
                  {awardLabel && (
                    <div
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--accent-text)",
                        letterSpacing: "0.08em",
                        marginBottom: 8,
                      }}
                    >
                      {awardLabel}
                    </div>
                  )}
                  <PaperCard paper={p} rank={i + 1} />
                </React.Fragment>
              );
            })}
          </div>
          <div ref={sentinelRef} style={{ height: 1 }} />
          {papersQ.isFetchingNextPage && (
            <div style={{ padding: "20px 0", textAlign: "center", color: "var(--ink-faint)" }}>
              Loading more…
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default ConferenceTaskView;

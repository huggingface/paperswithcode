import React, { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { PaperFeedList, PaperFeedToolbar } from "@/components/PaperFeed";
import MarkdownText from "@/components/MarkdownText";
import { catalogApi } from "@/lib/api/catalog";
import { papersApi } from "@/lib/api/papers";
import { isNotFound } from "@/lib/apiErrors";
import { CONFERENCE_LISTINGS } from "@/lib/conferenceListings";
import { paperQueryKeys } from "@/lib/paperQueryKeys";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { usePaperFeedParams } from "@/hooks/usePaperFeedParams";
import { usePaperFeedQuery } from "@/hooks/usePapers";
import { Alert, AlertDescription } from "@/components/ui/alert";
import NotFound from "@/pages/NotFound";
import { catalogQueryKeys, TEN_MINUTES } from "@/lib/api/queryKeys";

// Award announcements, keyed by `${conference}/${listing}`.
const AWARD_ANNOUNCEMENTS: Record<string, string> = {
  "iclr-2026/outstanding":
    "ICLR 2026 recognized two Outstanding Papers and one Honorable Mention. " +
    "[Read the announcement](https://blog.iclr.cc/2026/04/23/announcing-the-iclr-2026-outstanding-papers/).",
  "icml-2026/outstanding":
    "ICML 2026 recognized two Outstanding Papers and five Honorable Mentions. " +
    "[Read the announcement](https://blog.icml.cc/2026/07/05/announcing-the-icml-2026-awards/).",
  "cvpr-2026/best-paper-finalists":
    "CVPR 2026 recognized fifteen Best Paper Award finalists, including the winners. " +
    "[Read the announcement](https://x.com/CVPR/status/2062912519522717978).",
};

const ConferenceTaskView: React.FC = () => {
  const { confSlug, taskSlug } = useParams<{ confSlug: string; taskSlug: string }>();
  const feed = usePaperFeedParams();

  // Browse listings share this route with real task slugs.
  const listing = CONFERENCE_LISTINGS.find((candidate) => candidate.slug === taskSlug);
  const isAwardListing = !!listing?.award;

  const conferenceQ = useQuery({
    queryKey: ["conference", confSlug],
    queryFn: () => catalogApi.getConference(confSlug!),
    enabled: !!confSlug,
    staleTime: TEN_MINUTES,
  });

  const taskQ = useQuery({
    queryKey: catalogQueryKeys.task(taskSlug),
    queryFn: () => catalogApi.getTask(taskSlug!),
    enabled: !!taskSlug && !listing,
    staleTime: TEN_MINUTES,
  });

  const papersQ = usePaperFeedQuery(
    [...paperQueryKeys.feeds.conference, confSlug, taskSlug, feed.filters],
    (page) =>
      papersApi.forConference(confSlug!, {
        ...feed.filters,
        task: listing ? undefined : taskSlug,
        presentation: listing?.presentation,
        page,
        page_size: 12,
      }),
    { enabled: !!confSlug },
  );

  const papers = useMemo(
    () => papersQ.data?.pages.flatMap((page) => page.results) ?? [],
    [papersQ.data],
  );
  const cards = useMemo(() => papers.map(transformPaperForCard), [papers]);

  const taskName =
    listing?.label ??
    displayTaskName(taskQ.data?.name || taskSlug || "", taskQ.data?.slug || taskSlug);
  const announcement = AWARD_ANNOUNCEMENTS[`${confSlug}/${taskSlug}`];

  const totalCount = papersQ.data?.pages[0]?.count ?? conferenceQ.data?.paper_count ?? 0;
  const task = taskQ.data;

  if (isNotFound(conferenceQ.error) || isNotFound(taskQ.error)) return <NotFound />;
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

      <div className={!listing && task?.image_url ? "task-hero-grid" : undefined} style={{ marginTop: 16, marginBottom: 28 }}>
        <div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--accent-text)", letterSpacing: "0.1em", marginBottom: 8 }}>
            {listing ? "BROWSE PAPERS" : "TASK"}
          </div>
          <h1 className="domain-mega-title">{taskName}</h1>
          {announcement && <MarkdownText className="task-explainer" text={announcement} />}
          {!listing && task?.description && (
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
        {!listing && task?.image_url && (
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

      <PaperFeedToolbar feed={feed} sorts={isAwardListing ? null : undefined}>
        {!isAwardListing && (
          <div className="results-count">
            {cards.length} loaded in <span>{taskName}</span>
          </div>
        )}
      </PaperFeedToolbar>

      <PaperFeedList
        query={papersQ}
        cards={cards}
        empty="No papers found for this selection."
        cardHeader={(index) => {
          const award = papers[index]?.conference_award;
          const awardLabel =
            award === "outstanding"
              ? "Outstanding Paper"
              : award === "honorable_mention"
                ? "Honorable Mention"
                : award === "best_paper_finalist" && listing?.presentation !== "best_paper_finalist"
                  ? "Best Paper Finalist"
                  : null;
          return awardLabel && <div className="conference-award-label">{awardLabel}</div>;
        }}
      />
    </div>
  );
};

export default ConferenceTaskView;

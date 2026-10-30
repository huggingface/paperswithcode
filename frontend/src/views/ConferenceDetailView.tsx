import React, { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { AreaDirectoryFooter, AreaDirectorySkeleton, AreaSection } from "@/components/AreaSection";
import MarkdownText from "@/components/MarkdownText";
import { catalogApi } from "@/lib/api/catalog";
import { isNotFound } from "@/lib/apiErrors";
import { sortAreas } from "@/lib/areas";
import { chipColors, hueFromSlug } from "@/lib/colors";
import { CONFERENCE_LISTINGS } from "@/lib/conferenceListings";
import { formatDateRange } from "@/lib/deadlines";
import { displayTaskName } from "@/lib/transform";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { safeExternalHref } from "@/lib/safeExternalHref";
import NotFound from "@/pages/NotFound";
import { TEN_MINUTES } from "@/lib/api/queryKeys";

const ConferenceDetailView: React.FC = () => {
  const { confSlug } = useParams<{ confSlug: string }>();

  const taxonomyQ = useQuery({
    queryKey: ["conference-areas-with-tasks", confSlug],
    queryFn: () => catalogApi.conferenceAreasWithTasks(confSlug!),
    enabled: !!confSlug,
    staleTime: TEN_MINUTES,
  });

  const visibleAreas = useMemo(() => sortAreas(taxonomyQ.data?.results ?? []), [taxonomyQ.data]);

  const conference = taxonomyQ.data?.conference;
  const totalPapers = taxonomyQ.data?.total_paper_count ?? 0;
  const listings = CONFERENCE_LISTINGS.filter(
    (listing) => (taxonomyQ.data?.[listing.countKey] ?? 0) > 0,
  );

  if (isNotFound(taxonomyQ.error)) return <NotFound />;
  if (taxonomyQ.error) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Failed to load conference. Please try again.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const dates = conference ? formatDateRange(conference.start_date, conference.end_date) : null;
  const venueLine = conference
    ? [conference.venue, conference.location].filter(Boolean).join(", ")
    : null;

  const conferenceName = conference?.name;

  return (
    <div className="page">
      <div className={conference?.image_url ? "task-hero-grid" : undefined}>
        <div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--accent-text)", letterSpacing: "0.1em", marginBottom: 8 }}>
            CONFERENCE
          </div>
          <h1 className="feed-title">
            {conferenceName ?? <Skeleton className="h-10 w-64 inline-block" />}
          </h1>
          <div className="feed-subtitle" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {dates && <span>{dates}</span>}
            {venueLine && <span>{venueLine}</span>}
            {conference?.url && (
              <a href={safeExternalHref(conference.url) ?? undefined} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent-text)" }}>
                {conference.url.replace(/^https?:\/\//, "")}
              </a>
            )}
            {conference?.hf_url && (
              <a
                className="bm-action-btn"
                href={conference.hf_url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ alignSelf: "flex-start", marginTop: 4 }}
              >
                <span aria-hidden="true">🤗</span> View on Hugging Face
              </a>
            )}
          </div>
          {conference?.description && (
            <MarkdownText className="method-description" text={conference.description} />
          )}
        </div>
        {conference?.image_url && (
          <figure className="task-figure-card">
            <div className="task-figure-img-wrap">
              <img
                className="task-figure-img"
                src={conference.image_url}
                alt={conferenceName ? `${conferenceName} visual` : "Conference visual"}
                onError={(e) => {
                  (e.currentTarget.parentElement?.parentElement as HTMLElement | null)?.style.setProperty(
                    "display",
                    "none",
                  );
                }}
              />
            </div>
            <figcaption>
              Figure · {conferenceName ?? "Conference"}
              {conference.image_credit && (
                <>
                  <br />
                  <MarkdownText className="task-image-credit" text={conference.image_credit} />
                </>
              )}
            </figcaption>
          </figure>
        )}
      </div>

      {!taxonomyQ.isLoading && totalPapers > 0 && (
        <AreaSection
          title="Browse papers"
          description="All accepted papers, plus oral, spotlight, outstanding, and best paper finalists."
          meta={`${totalPapers.toLocaleString()} papers`}
          style={{ marginTop: 48 }}
        >
          {listings.map((listing) => (
            <Link key={listing.slug} to={`/conferences/${confSlug}/${listing.slug}`} className="tag-cell">
              <div className="name">
                <span className="dot" style={{ background: listing.dotColor }}></span>
                {listing.label}
              </div>
              <div className="meta">
                <span>{(taxonomyQ.data?.[listing.countKey] ?? 0).toLocaleString()} papers</span>
              </div>
            </Link>
          ))}
        </AreaSection>
      )}

      {taxonomyQ.isLoading ? (
        <AreaDirectorySkeleton tiles={6} tileClassName="h-24" />
      ) : (
        visibleAreas.map((area) => {
          const tasks = area.tasks;
          if (tasks.length === 0) return null;
          const areaPaperCount = tasks.reduce((s, t) => s + (t.paper_count || 0), 0);
          return (
            <AreaSection
              key={area.id}
              title={area.name}
              description={area.description}
              meta={`${tasks.length} ${tasks.length === 1 ? "task" : "tasks"} · ${areaPaperCount.toLocaleString()} papers`}
            >
              {tasks.map((t) => {
                const slug = t.slug || "";
                const c = chipColors(hueFromSlug(slug));
                return (
                  <Link
                    key={t.id}
                    to={`/conferences/${confSlug}/${slug}`}
                    className="tag-cell"
                  >
                    <div className="name">
                      <span className="dot" style={{ background: c.dot }}></span>
                      {displayTaskName(t.name, slug)}
                    </div>
                    <div className="meta">
                      <span>{(t.paper_count ?? 0).toLocaleString()} papers</span>
                    </div>
                  </Link>
                );
              })}
            </AreaSection>
          );
        })
      )}

      <AreaDirectoryFooter areas={visibleAreas} />
    </div>
  );
};

export default ConferenceDetailView;

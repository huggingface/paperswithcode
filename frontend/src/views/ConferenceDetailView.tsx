import React, { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import MarkdownText from "@/components/MarkdownText";
import { catalogApi } from "@/lib/api/catalog";
import { chipColors, hueFromSlug } from "@/lib/colors";
import { displayTaskName } from "@/lib/transform";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { safeExternalHref } from "@/lib/safeExternalHref";

const taskKey = (value?: string) => value?.trim().toLowerCase().replace(/[\s_]+/g, "-") ?? "";

const formatDateRange = (start?: string, end?: string) => {
  if (!start) return null;
  const startDate = new Date(`${start}T00:00:00`);
  const endDate = end ? new Date(`${end}T00:00:00`) : null;
  const monthDay = (d: Date) =>
    d.toLocaleDateString("en-US", { month: "long", day: "numeric" });
  const year = startDate.getFullYear();
  if (endDate && endDate.getTime() !== startDate.getTime()) {
    const sameMonth = startDate.getMonth() === endDate.getMonth();
    if (sameMonth) {
      return `${monthDay(startDate).replace(/\d+$/, "").trim()} ${startDate.getDate()}–${endDate.getDate()}, ${year}`;
    }
    return `${monthDay(startDate)} – ${monthDay(endDate)}, ${year}`;
  }
  return `${monthDay(startDate)}, ${year}`;
};

const ConferenceDetailView: React.FC = () => {
  const { confSlug } = useParams<{ confSlug: string }>();

  const taxonomyQ = useQuery({
    queryKey: ["conference-areas-with-tasks", confSlug],
    queryFn: () => catalogApi.conferenceAreasWithTasks(confSlug!),
    enabled: !!confSlug,
    staleTime: 10 * 60 * 1000,
  });

  const visibleAreas = useMemo(() => {
    if (!taxonomyQ.data) return [];

    const AREA_ORDER: Record<string, number> = {
      general: 0,
      vision: 1,
      video: 2,
      language: 3,
      audio: 4,
      other: 5,
    };
    const rank = (name: string) => AREA_ORDER[taskKey(name)] ?? 999;

    return [...taxonomyQ.data.results].sort((a, b) => {
      const ra = rank(a.name);
      const rb = rank(b.name);
      if (ra !== rb) return ra - rb;
      return a.name.localeCompare(b.name);
    });
  }, [taxonomyQ.data]);

  const conference = taxonomyQ.data?.conference;
  const totalPapers = taxonomyQ.data?.total_paper_count ?? 0;
  const oralPapers = taxonomyQ.data?.oral_paper_count ?? 0;
  const spotlightPapers = taxonomyQ.data?.spotlight_paper_count ?? 0;
  const outstandingPapers = taxonomyQ.data?.outstanding_paper_count ?? 0;
  const bestPaperFinalists = taxonomyQ.data?.best_paper_finalist_paper_count ?? 0;
  const totalTasks = visibleAreas.reduce((s, area) => s + area.tasks.length, 0);

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
        <section style={{ marginTop: 48, marginBottom: 48 }}>
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "6px 24px",
              paddingBottom: 12,
              borderBottom: "1px solid var(--hairline-strong)",
            }}
          >
            <div>
              <h2
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 26,
                  fontWeight: 500,
                  letterSpacing: "-0.02em",
                  marginBottom: 4,
                }}
              >
                Browse papers
              </h2>
              <div
                style={{
                  fontFamily: "var(--serif)",
                  fontStyle: "italic",
                  fontSize: 13,
                  color: "var(--ink-soft)",
                }}
              >
                All accepted papers, plus oral, spotlight, outstanding, and best paper finalists.
              </div>
            </div>
            <div
              style={{
                fontFamily: "var(--mono)",
                fontSize: 11,
                color: "var(--ink-faint)",
                whiteSpace: "nowrap",
              }}
            >
              {totalPapers.toLocaleString()} papers
            </div>
          </div>
          <div className="tag-grid">
            <Link to={`/conferences/${confSlug}/all`} className="tag-cell">
              <div className="name">
                <span className="dot" style={{ background: "var(--accent)" }}></span>
                All papers
              </div>
              <div className="meta">
                <span>{totalPapers.toLocaleString()} papers</span>
              </div>
            </Link>
            {oralPapers > 0 && (
              <Link to={`/conferences/${confSlug}/oral`} className="tag-cell">
                <div className="name">
                  <span className="dot" style={{ background: "#fdbb02" }}></span>
                  Oral papers
                </div>
                <div className="meta">
                  <span>{oralPapers.toLocaleString()} papers</span>
                </div>
              </Link>
            )}
            {spotlightPapers > 0 && (
              <Link to={`/conferences/${confSlug}/spotlight`} className="tag-cell">
                <div className="name">
                  <span className="dot" style={{ background: "#fdbb02" }}></span>
                  Spotlight papers
                </div>
                <div className="meta">
                  <span>{spotlightPapers.toLocaleString()} papers</span>
                </div>
              </Link>
            )}
            {outstandingPapers > 0 && (
              <Link to={`/conferences/${confSlug}/outstanding`} className="tag-cell">
                <div className="name">
                  <span className="dot" style={{ background: "#c45c26" }}></span>
                  Outstanding papers
                </div>
                <div className="meta">
                  <span>{outstandingPapers.toLocaleString()} papers</span>
                </div>
              </Link>
            )}
            {bestPaperFinalists > 0 && (
              <Link to={`/conferences/${confSlug}/best-paper-finalists`} className="tag-cell">
                <div className="name">
                  <span className="dot" style={{ background: "#c9a227" }}></span>
                  Best paper finalists
                </div>
                <div className="meta">
                  <span>{bestPaperFinalists.toLocaleString()} papers</span>
                </div>
              </Link>
            )}
          </div>
        </section>
      )}

      {taxonomyQ.isLoading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i}>
              <Skeleton className="h-8 w-1/3 mb-4" />
              <div className="tag-grid">
                {Array.from({ length: 6 }).map((__, j) => (
                  <Skeleton key={j} className="h-24" />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        visibleAreas.map((area) => {
          const tasks = area.tasks;
          if (tasks.length === 0) return null;
          const areaPaperCount = tasks.reduce((s, t) => s + (t.paper_count || 0), 0);
          return (
            <section key={area.id} style={{ marginBottom: 48 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: "6px 24px",
                  paddingBottom: 12,
                  borderBottom: "1px solid var(--hairline-strong)",
                }}
              >
                <div>
                  <h2
                    style={{
                      fontFamily: "var(--serif)",
                      fontSize: 26,
                      fontWeight: 500,
                      letterSpacing: "-0.02em",
                      marginBottom: 4,
                    }}
                  >
                    {area.name}
                  </h2>
                  {area.description && (
                    <div
                      style={{
                        fontFamily: "var(--serif)",
                        fontStyle: "italic",
                        fontSize: 13,
                        color: "var(--ink-soft)",
                      }}
                    >
                      {area.description}
                    </div>
                  )}
                </div>
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--ink-faint)",
                    whiteSpace: "nowrap",
                  }}
                >
                  {tasks.length} {tasks.length === 1 ? "task" : "tasks"} · {areaPaperCount.toLocaleString()} papers
                </div>
              </div>
              <div className="tag-grid">
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
              </div>
            </section>
          );
        })
      )}

      {totalTasks > 0 && (
        <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)", marginTop: 24 }}>
          {totalTasks} tasks across {visibleAreas.filter((area) => area.tasks.length > 0).length} areas.
        </div>
      )}
    </div>
  );
};

export default ConferenceDetailView;

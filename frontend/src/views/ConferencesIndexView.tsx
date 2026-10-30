import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import type { Conference } from "@/lib/api/catalog.types";
import { catalogApi } from "@/lib/api/catalog";
import { formatDateRange } from "@/lib/deadlines";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AreaDirectorySkeleton, AreaSection } from "@/components/AreaSection";
import { TaxonomySuggestionTile } from "@/components/TaxonomySuggestionTile";
import { TEN_MINUTES } from "@/lib/api/queryKeys";

const resolveConferenceYear = (conf: Conference): number => {
  if (conf.year != null) return conf.year;
  if (conf.start_date) return Number(conf.start_date.slice(0, 4));
  const slugYear = conf.slug.match(/-(\d{4})$/)?.[1];
  if (slugYear) return Number(slugYear);
  return 0;
};

const compareByStartDate = (a: Conference, b: Conference) => {
  if (a.start_date && b.start_date) {
    const cmp = a.start_date.localeCompare(b.start_date);
    if (cmp !== 0) return cmp;
  } else if (a.start_date) return -1;
  else if (b.start_date) return 1;
  return a.name.localeCompare(b.name);
};

const ConferencesIndexView: React.FC = () => {
  const conferencesQ = useQuery({
    queryKey: ["conferences"],
    queryFn: () => catalogApi.conferences(),
    staleTime: TEN_MINUTES,
  });

  const groupedByYear = useMemo(() => {
    if (!conferencesQ.data?.results) return null;
    const byYear: Record<number, Conference[]> = {};
    conferencesQ.data.results.forEach((conf) => {
      const year = resolveConferenceYear(conf);
      (byYear[year] ||= []).push(conf);
    });
    Object.values(byYear).forEach((arr) => arr.sort(compareByStartDate));
    return Object.keys(byYear)
      .map(Number)
      .sort((a, b) => b - a)
      .map((year) => ({ year, conferences: byYear[year] }));
  }, [conferencesQ.data]);

  if (conferencesQ.error) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Failed to load conferences. Please try again.</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            All <em>Conferences</em>
          </h1>
          <div className="feed-subtitle">
            Browse accepted papers from major AI conferences, grouped by research area and task.
          </div>
          <div className="conference-deadlines-link">
            Find deadlines for upcoming conferences{" "}
            <Link to="/ai-deadlines" className="underline underline-offset-2 hover:text-foreground">
              here
            </Link>
            . Conference information is based on{" "}
            <a
              href="https://huggingface.co/ai-conferences"
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-2 hover:text-foreground"
            >
              Hugging Face AI Conferences
            </a>
            .
          </div>
        </div>
      </div>

      {conferencesQ.isLoading ? (
        <AreaDirectorySkeleton sections={2} tiles={3} tileClassName="h-32" />
      ) : (
        groupedByYear?.map(({ year, conferences }) => {
          const totalPapers = conferences.reduce((s, c) => s + (c.paper_count ?? 0), 0);
          return (
            <AreaSection
              key={year}
              title={year > 0 ? String(year) : "Unknown year"}
              meta={`${conferences.length} ${conferences.length === 1 ? "conference" : "conferences"} · ${totalPapers.toLocaleString()} papers`}
            >
              {conferences.map((conf) => {
                const dates = formatDateRange(conf.start_date, conf.end_date);
                const venueLine = [conf.venue, conf.location].filter(Boolean).join(", ");
                return (
                  <Link key={conf.id} to={`/conferences/${conf.slug}`} className="tag-cell">
                    <div className="name">{conf.name}</div>
                    <div className="meta" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      {dates && <span>{dates}</span>}
                      {venueLine && <span>{venueLine}</span>}
                      <span>{(conf.paper_count ?? 0).toLocaleString()} papers</span>
                    </div>
                  </Link>
                );
              })}
              <TaxonomySuggestionTile kind="conference" />
            </AreaSection>
          );
        })
      )}
    </div>
  );
};

export default ConferencesIndexView;

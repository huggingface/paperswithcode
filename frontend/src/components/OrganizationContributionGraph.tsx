import React, { useEffect, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";

import { Skeleton } from "@/components/ui/skeleton";
import type { OrganizationContributions } from "@/lib/api/catalog.types";
import { catalogApi } from "@/lib/api/catalog";
import { TEN_MINUTES } from "@/lib/api/queryKeys";

const DAY_MS = 24 * 60 * 60 * 1000;
const CELL_SIZE = 12;
const CELL_GAP = 3;
const WEEKDAY_LABELS = new Map([
  [1, "Mon"],
  [3, "Wed"],
  [5, "Fri"],
]);

const parseDate = (value: string) => new Date(`${value}T00:00:00Z`);
const formatDateKey = (value: Date) => value.toISOString().slice(0, 10);

const contributionLevel = (count: number, thresholds: number[]) => {
  if (count === 0) return 0;
  const thresholdIndex = thresholds.findIndex((threshold) => count <= threshold);
  return thresholdIndex === -1 ? 4 : thresholdIndex + 1;
};

interface ContributionDay {
  key: string;
  date: Date;
  count: number;
  inRange: boolean;
  level: number;
}

const buildGraph = (data: OrganizationContributions) => {
  const start = parseDate(data.start_date);
  const end = parseDate(data.end_date);
  const gridStart = new Date(start.getTime() - start.getUTCDay() * DAY_MS);
  const gridEnd = new Date(
    end.getTime() + (6 - end.getUTCDay()) * DAY_MS,
  );
  const counts = new Map(
    data.results.map((item) => [item.date, item.paper_count]),
  );
  const positiveCounts = data.results
    .map((item) => item.paper_count)
    .sort((left, right) => left - right);
  const thresholds = [0.25, 0.5, 0.75].map(
    (percentile) =>
      positiveCounts[
        Math.min(
          positiveCounts.length - 1,
          Math.floor(positiveCounts.length * percentile),
        )
      ] ?? 1,
  );
  const days: ContributionDay[] = [];

  for (
    let timestamp = gridStart.getTime();
    timestamp <= gridEnd.getTime();
    timestamp += DAY_MS
  ) {
    const day = new Date(timestamp);
    const key = formatDateKey(day);
    const inRange = timestamp >= start.getTime() && timestamp <= end.getTime();
    const count = inRange ? counts.get(key) ?? 0 : 0;
    days.push({
      key,
      date: day,
      count,
      inRange,
      level: contributionLevel(count, thresholds),
    });
  }

  const weekCount = days.length / 7;
  const months: Array<{ label: string; column: number }> = [];
  let lastMonth = -1;
  for (let column = 0; column < weekCount; column += 1) {
    const week = days.slice(column * 7, column * 7 + 7);
    const firstInMonth = week.find(
      (day) =>
        day.inRange && (column === 0 || day.date.getUTCDate() <= 7),
    );
    if (firstInMonth && firstInMonth.date.getUTCMonth() !== lastMonth) {
      lastMonth = firstInMonth.date.getUTCMonth();
      if (
        months.length > 0 &&
        column - months[months.length - 1].column < 3
      ) {
        months.pop();
      }
      months.push({
        label: firstInMonth.date.toLocaleString("en", {
          month: "short",
          timeZone: "UTC",
        }),
        column,
      });
    }
  }

  return { days, months, weekCount };
};

export const ContributionGraphContent: React.FC<{
  data: OrganizationContributions;
  organizationName: string;
  title?: string;
  noun?: string;
}> = ({ data, organizationName, title = "Paper contributions", noun = "paper" }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const { days, months, weekCount } = useMemo(() => buildGraph(data), [data]);
  const graphWidth = weekCount * CELL_SIZE + (weekCount - 1) * CELL_GAP;

  useEffect(() => {
    const scrollArea = scrollRef.current;
    if (scrollArea) scrollArea.scrollLeft = scrollArea.scrollWidth;
  }, [weekCount]);

  return (
    <section
      className="organization-contributions"
      aria-labelledby="organization-contributions-title"
    >
      <div className="organization-contributions-header">
        <h2
          id="organization-contributions-title"
          className="organization-contributions-title"
        >
          {title}
        </h2>
        <p className="organization-contributions-summary">
          {data.total_count.toLocaleString()}{" "}
          {data.total_count === 1 ? noun : `${noun}s`} recorded in the last
          year
        </p>
      </div>

      <div className="organization-contributions-scroll" ref={scrollRef}>
        <div
          className="organization-contributions-plot"
          style={{ width: graphWidth + 34 }}
          role="img"
          aria-label={`${organizationName} recorded ${data.total_count} ${data.total_count === 1 ? noun : `${noun}s`} in the last year`}
        >
          <div className="organization-contributions-weekdays" aria-hidden="true">
            {Array.from({ length: 7 }).map((_, day) => (
              <span key={day}>{WEEKDAY_LABELS.get(day) ?? ""}</span>
            ))}
          </div>
          <div>
            <div
              className="organization-contributions-months"
              style={{
                width: graphWidth,
                gridTemplateColumns: `repeat(${weekCount}, ${CELL_SIZE}px)`,
              }}
              aria-hidden="true"
            >
              {months.map((month) => (
                <span
                  key={`${month.label}-${month.column}`}
                  style={{ gridColumnStart: month.column + 1 }}
                >
                  {month.label}
                </span>
              ))}
            </div>
            <div
              className="organization-contributions-grid"
              style={{
                width: graphWidth,
                gridTemplateColumns: `repeat(${weekCount}, ${CELL_SIZE}px)`,
              }}
              aria-hidden="true"
            >
              {days.map((day) => (
                <span
                  key={day.key}
                  className={`organization-contribution-cell ${
                    day.inRange ? `level-${day.level}` : "is-outside"
                  }`}
                  title={
                    day.inRange
                      ? `${day.count} ${day.count === 1 ? noun : `${noun}s`} on ${day.date.toLocaleDateString("en", { dateStyle: "long", timeZone: "UTC" })}`
                      : undefined
                  }
                />
              ))}
            </div>
          </div>
        </div>
      </div>
      <div className="organization-contributions-legend" aria-hidden="true">
        <span>Fewer</span>
        {[0, 1, 2, 3, 4].map((level) => (
          <span
            key={level}
            className={`organization-contribution-cell level-${level}`}
          />
        ))}
        <span>More</span>
      </div>
    </section>
  );
};

export const OrganizationContributionGraph: React.FC<{
  organizationSlug: string;
  organizationName: string;
}> = ({ organizationSlug, organizationName }) => {
  const contributionsQ = useQuery({
    queryKey: ["organization-contributions", organizationSlug],
    queryFn: () => catalogApi.organizationContributions(organizationSlug),
    staleTime: TEN_MINUTES,
  });

  if (contributionsQ.isLoading) {
    return <Skeleton className="organization-contributions-skeleton" />;
  }
  if (!contributionsQ.data) return null;

  return (
    <ContributionGraphContent
      data={contributionsQ.data}
      organizationName={organizationName}
    />
  );
};

import React, { useEffect, useMemo, useState } from "react";

import type { Conference, ConferenceDeadline } from "@/lib/api/catalog.types";
import { safeExternalHref } from "@/lib/safeExternalHref";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  conferenceDomains,
  DAY_MS,
  formatDateRange,
  formatDeadlineDate,
  labelFromTag,
  nextUpcomingDeadline,
  preciseCountdown,
  sortedDeadlines,
  urgencyColor,
} from "@/lib/deadlines";

const monoLabel: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 10,
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  color: "var(--ink-faint)",
};

const daysRemainingLabel = (target: number, now: number): string => {
  const days = Math.ceil((target - now) / DAY_MS);
  if (days <= 0) return "passed";
  return `${days} ${days === 1 ? "day" : "days"}`;
};

const buildCalendarDescription = (conf: Conference, deadline: ConferenceDeadline) => {
  const dateRange = formatDateRange(conf.start_date, conf.end_date);
  const location = conf.venue || [conf.city, conf.country].filter(Boolean).join(", ");
  return [
    `${deadline.label || deadline.type || "Deadline"} for ${conf.name}`,
    dateRange ? `Dates: ${dateRange}` : null,
    location ? `Location: ${location}` : null,
    conf.url ? `Website: ${conf.url}` : null,
  ]
    .filter(Boolean)
    .join("\n");
};

const formatICSDate = (d: Date) =>
  d
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}/, "");

const addToGoogleCalendar = (conf: Conference, deadline: ConferenceDeadline) => {
  const start = new Date(deadline.deadline_at);
  const end = new Date(start.getTime() + 60 * 60 * 1000);
  const title = `${conf.short_name || conf.name} ${deadline.label || deadline.type || "deadline"}`;
  const location = conf.venue || [conf.city, conf.country].filter(Boolean).join(", ");
  const url =
    `https://calendar.google.com/calendar/render?action=TEMPLATE` +
    `&text=${encodeURIComponent(title)}` +
    `&dates=${formatICSDate(start)}/${formatICSDate(end)}` +
    `&details=${encodeURIComponent(buildCalendarDescription(conf, deadline))}` +
    `&location=${encodeURIComponent(location)}`;
  const safeUrl = safeExternalHref(url);
  if (safeUrl) window.open(safeUrl, "_blank", "noopener,noreferrer");
};

const downloadICS = (conf: Conference, deadline: ConferenceDeadline) => {
  const start = new Date(deadline.deadline_at);
  const end = new Date(start.getTime() + 60 * 60 * 1000);
  const title = `${conf.short_name || conf.name} ${deadline.label || deadline.type || "deadline"}`;
  const location = conf.venue || [conf.city, conf.country].filter(Boolean).join(", ");
  const ics = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "BEGIN:VEVENT",
    conf.url ? `URL:${conf.url}` : null,
    `DTSTART:${formatICSDate(start)}`,
    `DTEND:${formatICSDate(end)}`,
    `SUMMARY:${title}`,
    `DESCRIPTION:${buildCalendarDescription(conf, deadline).replace(/\n/g, "\\n")}`,
    location ? `LOCATION:${location}` : null,
    "END:VEVENT",
    "END:VCALENDAR",
  ]
    .filter(Boolean)
    .join("\n");

  const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${(conf.short_name || conf.name).toLowerCase().replace(/\s+/g, "-")}-deadline.ics`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
};

const ConferenceDeadlineDialog: React.FC<{
  conf: Conference | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}> = ({ conf, open, onOpenChange }) => {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!open) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [open]);

  const deadlines = useMemo(() => (conf ? sortedDeadlines(conf) : []), [conf]);
  const next = useMemo(
    () => (conf ? nextUpcomingDeadline(conf, now) : null),
    [conf, now],
  );

  const dateRange = conf ? formatDateRange(conf.start_date, conf.end_date) : null;
  const location = conf
    ? conf.venue || [conf.city, conf.country].filter(Boolean).join(", ") || conf.location
    : null;
  const nextTime = next ? new Date(next.deadline_at).getTime() : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-xl"
        style={{ background: "var(--bg-elevated)", maxHeight: "85vh", overflowY: "auto" }}
      >
        {conf && (
          <>
            <DialogHeader>
              <DialogTitle asChild>
                <h2
                  style={{
                    fontFamily: "var(--serif)",
                    fontSize: 26,
                    fontWeight: 500,
                    letterSpacing: "-0.01em",
                    margin: 0,
                  }}
                >
                  {conf.short_name
                    ? `${conf.short_name} ${conf.year ?? ""}`.trim()
                    : conf.name}
                </h2>
              </DialogTitle>
              {(conf.short_name && conf.name) || conf.description ? (
                <DialogDescription asChild>
                  <span
                    style={{
                      fontFamily: "var(--serif)",
                      fontSize: 14,
                      color: "var(--ink-soft)",
                    }}
                  >
                    {conf.short_name ? conf.name : conf.description}
                  </span>
                </DialogDescription>
              ) : null}
            </DialogHeader>

            <div style={{ display: "flex", flexDirection: "column", gap: 20, marginTop: 4 }}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 24 }}>
                {dateRange && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={monoLabel}>Dates</span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--ink-soft)" }}>
                      {dateRange}
                    </span>
                  </div>
                )}
                {location && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={monoLabel}>Venue</span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--ink-soft)" }}>
                      {location}
                    </span>
                  </div>
                )}
              </div>

              {nextTime != null && (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                    padding: "12px 14px",
                    borderRadius: 8,
                    background: "var(--bg-subtle)",
                    border: "1px solid var(--hairline)",
                  }}
                >
                  <span style={monoLabel}>Next deadline in</span>
                  <span
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 22,
                      fontWeight: 600,
                      color: urgencyColor(nextTime, now),
                    }}
                  >
                    {preciseCountdown(nextTime, now)}
                  </span>
                </div>
              )}

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <span style={monoLabel}>Important deadlines</span>
                {deadlines.length === 0 ? (
                  <span style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--ink-faint)" }}>
                    Deadlines not announced yet
                  </span>
                ) : (
                  deadlines.map((d, i) => {
                    const time = new Date(d.deadline_at).getTime();
                    const isNext =
                      next != null &&
                      d.deadline_at === next.deadline_at &&
                      d.type === next.type;
                    const passed = time <= now;
                    return (
                      <div
                        key={`${d.type ?? "deadline"}-${i}`}
                        style={{
                          display: "flex",
                          alignItems: "baseline",
                          justifyContent: "space-between",
                          gap: 12,
                          padding: "8px 12px",
                          borderRadius: 6,
                          background: isNext ? "var(--accent-soft)" : "transparent",
                          border: isNext
                            ? "1px solid var(--hairline-strong)"
                            : "1px solid var(--hairline)",
                          opacity: passed && !isNext ? 0.55 : 1,
                        }}
                      >
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <span
                            style={{
                              fontFamily: "var(--mono)",
                              fontSize: 13,
                              color: "var(--ink)",
                              fontWeight: isNext ? 600 : 400,
                            }}
                          >
                            {d.label || labelFromTag(d.type || "deadline")}
                            {isNext && (
                              <span style={{ ...monoLabel, marginLeft: 8 }}>Next</span>
                            )}
                          </span>
                          <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-faint)" }}>
                            {formatDeadlineDate(d.deadline_at)}
                            {d.timezone ? ` · ${d.timezone}` : ""}
                          </span>
                        </div>
                        <span
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 12,
                            fontWeight: 600,
                            whiteSpace: "nowrap",
                            color: urgencyColor(passed ? null : time, now),
                          }}
                        >
                          {daysRemainingLabel(time, now)}
                        </span>
                      </div>
                    );
                  })
                )}
              </div>

              {conferenceDomains(conf).length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {conferenceDomains(conf).map((tag) => (
                    <span
                      key={tag}
                      className="tag-chip"
                      style={{ background: "var(--bg-subtle)", color: "var(--ink-soft)" }}
                    >
                      {labelFromTag(tag)}
                    </span>
                  ))}
                </div>
              )}

              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  alignItems: "center",
                  gap: 16,
                  paddingTop: 12,
                  borderTop: "1px solid var(--hairline)",
                }}
              >
                {conf.url && (
                  <a
                    href={safeExternalHref(conf.url) ?? undefined}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 12,
                      color: "var(--accent-text)",
                    }}
                  >
                    Visit website ↗
                  </a>
                )}
                {next && (
                  <div style={{ display: "flex", gap: 12, marginLeft: "auto" }}>
                    <button
                      type="button"
                      className="tag-chip"
                      onClick={() => addToGoogleCalendar(conf, next)}
                      style={{ background: "var(--bg-subtle)", color: "var(--ink-soft)" }}
                    >
                      + Google Calendar
                    </button>
                    <button
                      type="button"
                      className="tag-chip"
                      onClick={() => downloadICS(conf, next)}
                      style={{ background: "var(--bg-subtle)", color: "var(--ink-soft)" }}
                    >
                      + Apple / .ics
                    </button>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default ConferenceDeadlineDialog;

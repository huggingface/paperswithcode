import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import type { Conference } from "@/lib/api/catalog.types";
import { catalogApi } from "@/lib/api/catalog";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import ConferenceDeadlineDialog from "@/components/ai-deadlines/ConferenceDeadlineDialog";
import { safeExternalHref } from "@/lib/safeExternalHref";
import {
  conferenceDomains,
  countdownLabel,
  formatDateRange,
  formatDeadlineDate,
  labelFromTag,
  latestDeadline,
  nextUpcomingDeadline,
  urgencyColor,
} from "@/lib/deadlines";
import { TEN_MINUTES } from "@/lib/api/queryKeys";

const Toggle: React.FC<{
  id: string;
  label: React.ReactNode;
  checked: boolean;
  onChange: (v: boolean) => void;
}> = ({ id, label, checked, onChange }) => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      gap: 8,
      fontFamily: "var(--mono)",
      fontSize: 12,
      color: "var(--ink-soft)",
    }}
  >
    <Switch id={id} checked={checked} onCheckedChange={onChange} />
    <label htmlFor={id} style={{ cursor: "pointer" }}>
      {label}
    </label>
  </div>
);

const DeadlineCard: React.FC<{
  conf: Conference;
  now: number;
  selectedDomains: Set<string>;
  onToggleDomain: (tag: string) => void;
  onOpen: (conf: Conference) => void;
}> = ({ conf, now, selectedDomains, onToggleDomain, onOpen }) => {
  const next = nextUpcomingDeadline(conf, now);
  const primary = next ?? latestDeadline(conf);
  const primaryTime = primary ? new Date(primary.deadline_at).getTime() : null;
  const color = urgencyColor(next ? primaryTime : null, now);
  const dateRange = formatDateRange(conf.start_date, conf.end_date);
  const location = [conf.city ?? null, conf.country ?? null]
    .filter(Boolean)
    .join(", ");

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpen(conf)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(conf);
        }
      }}
      style={{
        border: "1px solid var(--hairline)",
        borderRadius: 8,
        padding: 20,
        background: "var(--bg-elevated)",
        display: "flex",
        flexDirection: "column",
        gap: 12,
        cursor: "pointer",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: 12,
        }}
      >
        <h3
          style={{
            fontFamily: "var(--serif)",
            fontSize: 20,
            fontWeight: 500,
            letterSpacing: "-0.01em",
            margin: 0,
          }}
        >
          {conf.short_name ? `${conf.short_name} ${conf.year ?? ""}`.trim() : conf.name}
        </h3>
        {conf.url && (
          <a
            href={safeExternalHref(conf.url) ?? undefined}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            style={{
              fontFamily: "var(--mono)",
              fontSize: 11,
              color: "var(--accent-text)",
              whiteSpace: "nowrap",
            }}
          >
            website ↗
          </a>
        )}
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: 12,
          paddingBottom: 12,
          borderBottom: "1px solid var(--hairline)",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span
            style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)" }}
          >
            {primary?.label || primary?.type || "Deadline"}
          </span>
          <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-soft)" }}>
            {primary
              ? `${formatDeadlineDate(primary.deadline_at)}${
                  primary.timezone ? ` · ${primary.timezone}` : ""
                }`
              : "TBD"}
          </span>
        </div>
        <span
          style={{
            fontFamily: "var(--mono)",
            fontSize: 14,
            fontWeight: 600,
            color,
            whiteSpace: "nowrap",
          }}
        >
          {primaryTime != null ? countdownLabel(primaryTime, now) : "TBD"}
        </span>
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 4,
          fontFamily: "var(--mono)",
          fontSize: 11,
          color: "var(--ink-faint)",
        }}
      >
        {dateRange && <span>{dateRange}</span>}
        {location && <span>{location}</span>}
      </div>

      {conferenceDomains(conf).length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {conferenceDomains(conf).map((tag) => {
            const active = selectedDomains.has(tag);
            return (
              <button
                key={tag}
                className="tag-chip"
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleDomain(tag);
                }}
                style={{
                  background: active ? "var(--ink)" : "var(--bg-subtle)",
                  color: active ? "var(--bg)" : "var(--ink-soft)",
                }}
              >
                {labelFromTag(tag)}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

const AiDeadlinesView: React.FC = () => {
  const [showTopTierOnly, setShowTopTierOnly] = useState(true);
  const [showPast, setShowPast] = useState(false);
  const [selectedDomains, setSelectedDomains] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Conference | null>(null);

  // Single fixed reference time so countdowns/sorting are stable per render.
  const now = useMemo(() => Date.now(), []);

  const deadlinesQ = useQuery({
    queryKey: ["conference-deadlines"],
    queryFn: () => catalogApi.conferenceDeadlines(),
    staleTime: TEN_MINUTES,
  });

  const toggleDomain = (tag: string) => {
    setSelectedDomains((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  };

  const allDomains = useMemo(() => {
    const counts = new Map<string, number>();
    deadlinesQ.data?.results.forEach((conf) => {
      conferenceDomains(conf).forEach((tag) =>
        counts.set(tag, (counts.get(tag) ?? 0) + 1),
      );
    });
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([tag]) => tag);
  }, [deadlinesQ.data]);

  const conferences = useMemo(() => {
    const all = deadlinesQ.data?.results ?? [];
    const filtered = all.filter((conf) => {
      if (showTopTierOnly && conf.tier !== "a") return false;
      if (selectedDomains.size > 0) {
        const hasDomain = conferenceDomains(conf).some((t) =>
          selectedDomains.has(t),
        );
        if (!hasDomain) return false;
      }
      if (!showPast && !nextUpcomingDeadline(conf, now)) return false;
      return true;
    });

    const sortKey = (conf: Conference) => {
      const next = nextUpcomingDeadline(conf, now);
      if (next) return { group: 0, time: new Date(next.deadline_at).getTime() };
      const latest = latestDeadline(conf);
      // Past-only conferences sink below upcoming ones, most recent first.
      return { group: 1, time: -(latest ? new Date(latest.deadline_at).getTime() : 0) };
    };

    return [...filtered].sort((a, b) => {
      const ka = sortKey(a);
      const kb = sortKey(b);
      if (ka.group !== kb.group) return ka.group - kb.group;
      return ka.time - kb.time;
    });
  }, [deadlinesQ.data, showTopTierOnly, showPast, selectedDomains, now]);

  if (deadlinesQ.error) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>
            Failed to load conference deadlines. Please try again.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            AI Conference <em>Deadlines</em>
          </h1>
          <div className="feed-subtitle">
            Upcoming submission deadlines for major AI conferences, counting down.
          </div>
        </div>
      </div>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: 20,
          padding: "16px 0",
          borderBottom: "1px solid var(--hairline)",
          marginBottom: 24,
        }}
      >
        <Toggle
          id="top-tier-only"
          label="Top tier only"
          checked={showTopTierOnly}
          onChange={setShowTopTierOnly}
        />
        <Toggle
          id="show-past"
          label="Show past conferences"
          checked={showPast}
          onChange={setShowPast}
        />
      </div>

      {allDomains.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 24 }}>
          {allDomains.map((tag) => {
            const active = selectedDomains.has(tag);
            return (
              <button
                key={tag}
                className="tag-chip"
                onClick={() => toggleDomain(tag)}
                style={{
                  background: active ? "var(--ink)" : "var(--bg-subtle)",
                  color: active ? "var(--bg)" : "var(--ink-soft)",
                }}
              >
                {labelFromTag(tag)}
              </button>
            );
          })}
          {selectedDomains.size > 0 && (
            <button
              className="tag-chip"
              onClick={() => setSelectedDomains(new Set())}
              style={{ background: "transparent", color: "var(--ink-faint)" }}
            >
              Clear ✕
            </button>
          )}
        </div>
      )}

      <div className="sort-bar">
        <div className="results-count">
          {deadlinesQ.isLoading ? "…" : `${conferences.length} conferences`}
        </div>
      </div>

      {deadlinesQ.isLoading ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: 16,
          }}
        >
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-44" />
          ))}
        </div>
      ) : conferences.length === 0 ? (
        <div className="no-results">
          No conferences match these filters
          {!showPast ? " — try enabling \u201cShow past conferences\u201d." : "."}
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: 16,
          }}
        >
          {conferences.map((conf) => (
            <DeadlineCard
              key={conf.id}
              conf={conf}
              now={now}
              selectedDomains={selectedDomains}
              onToggleDomain={toggleDomain}
              onOpen={setSelected}
            />
          ))}
        </div>
      )}

      <ConferenceDeadlineDialog
        conf={selected}
        open={selected !== null}
        onOpenChange={(o) => {
          if (!o) setSelected(null);
        }}
      />
    </div>
  );
};

export default AiDeadlinesView;

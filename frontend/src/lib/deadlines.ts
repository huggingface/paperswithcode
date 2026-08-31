import type { Conference, ConferenceDeadline } from "@/lib/api/catalog.types";

export const DAY_MS = 1000 * 60 * 60 * 24;

const URGENCY = {
  urgent: "#c0392b", // <= 7 days
  soon: "#b9770e", // <= 30 days
  normal: "#3f7d3f", // > 30 days
  passed: "var(--ink-faint)",
} as const;

export const labelFromTag = (tag: string) =>
  tag
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");

// Canonical AI-domain tags surfaced as filters/chips. The source data also
// contains malformed or one-off tags (e.g. "software engineering", free-text
// duplicates like "machine learning"); only recognized research domains are
// shown, matching the categories surfaced on the ai-deadlines space.
const DOMAIN_ALLOWLIST = new Set<string>([
  "machine-learning",
  "computer-vision",
  "natural-language-processing",
  "data-mining",
  "robotics",
  "computer-graphics",
  "human-computer-interaction",
  "web-search",
  "signal-processing",
  "representation-learning",
  "reinforcement-learning",
  "optimization-methods",
  "large-language-models",
  "information-retrieval",
  "speech",
  "mathematics",
]);

const normalizeTag = (tag: string) =>
  tag.trim().toLowerCase().replace(/\s+/g, "-");

// Normalized, allowlisted, de-duplicated domain tags for a conference.
export const conferenceDomains = (conf: Conference): string[] =>
  Array.from(
    new Set(
      (conf.tags ?? [])
        .map(normalizeTag)
        .filter((t) => DOMAIN_ALLOWLIST.has(t)),
    ),
  );

export const formatDeadlineDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

export const formatDateRange = (start?: string, end?: string): string | null => {
  if (!start) return null;
  const startDate = new Date(`${start}T00:00:00`);
  const endDate = end ? new Date(`${end}T00:00:00`) : null;
  const monthDay = (d: Date) =>
    d.toLocaleDateString("en-US", { month: "long", day: "numeric" });
  const year = startDate.getFullYear();
  if (endDate && endDate.getTime() !== startDate.getTime()) {
    const sameMonth = startDate.getMonth() === endDate.getMonth();
    if (sameMonth) {
      const monthName = monthDay(startDate).replace(/\d+$/, "").trim();
      return `${monthName} ${startDate.getDate()}–${endDate.getDate()}, ${year}`;
    }
    return `${monthDay(startDate)} – ${monthDay(endDate)}, ${year}`;
  }
  return `${monthDay(startDate)}, ${year}`;
};

export const sortedDeadlines = (conf: Conference): ConferenceDeadline[] =>
  [...(conf.deadlines ?? [])].sort(
    (a, b) => new Date(a.deadline_at).getTime() - new Date(b.deadline_at).getTime(),
  );

export const nextUpcomingDeadline = (
  conf: Conference,
  now: number,
): ConferenceDeadline | null =>
  sortedDeadlines(conf).find((d) => new Date(d.deadline_at).getTime() > now) ?? null;

export const latestDeadline = (conf: Conference): ConferenceDeadline | null => {
  const all = sortedDeadlines(conf);
  return all.length ? all[all.length - 1] : null;
};

export const countdownLabel = (target: number, now: number): string => {
  const diff = target - now;
  if (diff <= 0) return "Deadline passed";
  const days = Math.floor(diff / DAY_MS);
  if (days >= 1) {
    const hours = Math.floor((diff - days * DAY_MS) / (1000 * 60 * 60));
    return `in ${days}d ${hours}h`;
  }
  const hours = Math.floor(diff / (1000 * 60 * 60));
  if (hours >= 1) return `in ${hours}h`;
  const minutes = Math.max(1, Math.floor(diff / (1000 * 60)));
  return `in ${minutes}m`;
};

export const preciseCountdown = (target: number, now: number): string => {
  const diff = target - now;
  if (diff <= 0) return "Deadline passed";
  const days = Math.floor(diff / DAY_MS);
  const hours = Math.floor((diff % DAY_MS) / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
  const seconds = Math.floor((diff % (1000 * 60)) / 1000);
  return `${days}d ${hours}h ${minutes}m ${seconds}s`;
};

export const urgencyColor = (target: number | null, now: number): string => {
  if (target == null) return URGENCY.passed;
  const days = (target - now) / DAY_MS;
  if (days <= 0) return URGENCY.passed;
  if (days <= 7) return URGENCY.urgent;
  if (days <= 30) return URGENCY.soon;
  return URGENCY.normal;
};

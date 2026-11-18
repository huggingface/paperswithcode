/**
 * Document titles for SPA navigations. They mirror the titles the server
 * injects on first load (backend/services/discovery_page_service.py), so a
 * page keeps the same title whether it was opened directly or navigated to.
 */
import { DEFAULT_SITE_SUFFIX } from "@/lib/latexPlainText";

const withSuffix = (title: string) => `${title} | ${DEFAULT_SITE_SUFFIX}`;

export const HOME_PAGE_TITLE = `${DEFAULT_SITE_SUFFIX} — Trending research and open source`;

export const INDEX_PAGE_TITLES = {
  tasks: withSuffix("Machine Learning Tasks and Benchmarks"),
  methods: withSuffix("Machine Learning Methods"),
  conferences: withSuffix("AI Conferences and Accepted Papers"),
  organizations: withSuffix("AI Research Organizations"),
  frameworks: withSuffix("Machine Learning Frameworks"),
  trends: withSuffix("Machine Learning Research Trends"),
  aiDeadlines: withSuffix("AI Conference Deadlines 2026"),
} as const;

/** Task, method, conference, organization and author pages. */
export const entityPageTitle = (name: string) => withSuffix(`${name} — papers and benchmarks`);

/** Tasks with ranked benchmark leaders get the "Best … Models" title. */
export function taskPageTitle(name: string, hasLeaders: boolean, today = new Date()) {
  if (!hasLeaders) return entityPageTitle(name);
  const month = today.toLocaleDateString("en-US", { month: "long", year: "numeric" });
  return withSuffix(`Best ${name} Models (${month}): leaderboards and papers`);
}

export const benchmarkPageTitle = (name: string) =>
  withSuffix(`${name} Leaderboard: state of the art results`);

export const papersPageTitle = (heading: string) => withSuffix(heading);

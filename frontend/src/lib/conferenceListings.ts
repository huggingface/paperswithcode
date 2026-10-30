import type { ConferenceAreasWithTasks } from "@/lib/api/catalog.types";

export type ConferencePresentation = "oral" | "spotlight" | "outstanding" | "best_paper_finalist";

interface ConferenceListing {
  /** Route segment under /conferences/:confSlug/. */
  slug: string;
  label: string;
  presentation?: ConferencePresentation;
  /** Award listings are curated sets, so they hide sorting. */
  award?: boolean;
  dotColor: string;
  countKey: keyof Pick<
    ConferenceAreasWithTasks,
    | "total_paper_count"
    | "oral_paper_count"
    | "spotlight_paper_count"
    | "outstanding_paper_count"
    | "best_paper_finalist_paper_count"
  >;
}

/** Browse listings that share the conference task route with real task slugs. */
export const CONFERENCE_LISTINGS: readonly ConferenceListing[] = [
  { slug: "all", label: "All papers", dotColor: "var(--accent)", countKey: "total_paper_count" },
  { slug: "oral", label: "Oral papers", presentation: "oral", dotColor: "#fdbb02", countKey: "oral_paper_count" },
  { slug: "spotlight", label: "Spotlight papers", presentation: "spotlight", dotColor: "#fdbb02", countKey: "spotlight_paper_count" },
  { slug: "outstanding", label: "Outstanding papers", presentation: "outstanding", award: true, dotColor: "#c45c26", countKey: "outstanding_paper_count" },
  { slug: "best-paper-finalists", label: "Best paper finalists", presentation: "best_paper_finalist", award: true, dotColor: "#c9a227", countKey: "best_paper_finalist_paper_count" },
];

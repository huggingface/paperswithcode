import { useSearchParams } from "react-router-dom";

import {
  readPaperDateRange,
  withPaperDateRange,
  type PaperDateRangeValue,
} from "@/lib/paperDateRange";

export type PaperFeedSort = "trending" | "date_published" | "citation_count";

export const PAPER_FEED_SORTS: ReadonlyArray<readonly [PaperFeedSort, string]> = [
  ["trending", "trending"],
  ["date_published", "newest"],
  ["citation_count", "most cited"],
];

/** A paper feed's sort, resource toggles and date range, kept in the URL so feeds stay shareable. */
export function usePaperFeedParams() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("order_by");
  const orderBy: PaperFeedSort =
    requested === "date_published" || requested === "citation_count" ? requested : "trending";
  const hasCode = searchParams.get("has_code") === "true";
  const hasHfArtifacts = searchParams.get("has_hf_artifacts") === "true";
  const dateRange = readPaperDateRange(searchParams);

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
  };

  return {
    searchParams,
    setSearchParams,
    orderBy,
    hasCode,
    hasHfArtifacts,
    dateRange,
    setOrderBy: (value: string) => setParam("order_by", value === "trending" ? null : value),
    setHasCode: (active: boolean) => setParam("has_code", active ? "true" : null),
    setHasHfArtifacts: (active: boolean) => setParam("has_hf_artifacts", active ? "true" : null),
    setDateRange: (value: PaperDateRangeValue) =>
      setSearchParams(withPaperDateRange(searchParams, value)),
    /** Request parameters every paper feed endpoint accepts. */
    filters: {
      order_by: orderBy,
      order_dir: "desc" as const,
      latest_only: true,
      include_resources: true,
      has_code: hasCode,
      has_hf_artifacts: hasHfArtifacts,
      start_date: dateRange.startDate,
      end_date: dateRange.endDate,
    },
  };
}

export type PaperFeedParams = ReturnType<typeof usePaperFeedParams>;

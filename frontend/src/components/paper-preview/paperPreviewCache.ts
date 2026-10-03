import { paperQueryKeys } from "@/lib/paperQueryKeys";
import type { QueryClient } from "@tanstack/react-query";

import { papersApi } from "@/lib/api/papers";
import type { Paper, PaperReferenceQuery } from "@/lib/api/papers.types";
import { normalizePaperRouteId } from "@/lib/utils";

export const paperPreviewQueryKey = (routeId: string) =>
  paperQueryKeys.preview(normalizePaperRouteId(routeId));

export const paperRouteId = (paper: Paper): string => paper.arxiv_id ?? paper.id;

// The backend accepts 500 entries per request; keep well under that.
const LOOKUP_BATCH = 200;

export interface PaperPreviewCache {
  /** Resolve bibliography entries in bulk and cache every matched card. Returns key → route id. */
  lookup(references: PaperReferenceQuery[]): Promise<Map<string, string>>;
  /** Cache cards for arXiv ids that are about to become hoverable, once each. */
  warm(routeIds: string[]): void;
}

// Preview cards read the ["paper-preview", routeId] query, so seeding it here
// means hovering never shows a loading state for a card we already fetched.
export function createPaperPreviewCache(queryClient: QueryClient, api: Pick<typeof papersApi, "lookup"> = papersApi): PaperPreviewCache {
  const requested = new Set<string>();
  const lookup = async (references: PaperReferenceQuery[]) => {
    const matches = new Map<string, string>();
    for (const reference of references) {
      if (reference.arxiv_id) requested.add(normalizePaperRouteId(reference.arxiv_id));
    }
    for (let start = 0; start < references.length; start += LOOKUP_BATCH) {
      const { references: resolved } = await api.lookup(references.slice(start, start + LOOKUP_BATCH));
      for (const entry of resolved) {
        if (!entry.paper) continue;
        const routeId = paperRouteId(entry.paper);
        queryClient.setQueryData(paperPreviewQueryKey(routeId), entry.paper);
        matches.set(entry.key, routeId);
      }
    }
    return matches;
  };
  const warm = (routeIds: string[]) => {
    const missing = routeIds.filter(routeId => {
      const key = normalizePaperRouteId(routeId);
      if (requested.has(key) || queryClient.getQueryData(paperPreviewQueryKey(key))) return false;
      requested.add(key);
      return true;
    });
    if (missing.length) void lookup(missing.map(routeId => ({ key: routeId, arxiv_id: routeId }))).catch(() => undefined);
  };
  return { lookup, warm };
}

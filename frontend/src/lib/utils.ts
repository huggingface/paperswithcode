import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Normalize `/paper/:id` route segments (e.g. `2606-02800` -> `2606.02800`). */
export function normalizePaperRouteId(routeId: string): string {
  const trimmed = routeId.trim();
  const dashMatch = trimmed.match(/^(\d{4})-(\d{4,5})(v\d+)?$/);
  if (dashMatch) {
    return `${dashMatch[1]}.${dashMatch[2]}`;
  }
  const versionMatch = trimmed.match(/^(\d{4}\.\d{4,5})(v\d+)$/);
  if (versionMatch) {
    return versionMatch[1];
  }
  return trimmed;
}

// Preserve thousandths for fractional metrics such as AbsRel and Pass@1, with
// fewer decimals for larger magnitudes so headline numbers stay readable. Accepts
// strings (as returned by the evaluations API) and falls back to the raw value
// when it isn't a finite number.
export function formatMetricValue(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (!Number.isFinite(n)) return String(v);
  if (Math.abs(n) >= 100) return n.toFixed(0);
  if (Math.abs(n) >= 10) return n.toFixed(1);
  if (Math.abs(n) < 1) return n.toFixed(3);
  return n.toFixed(2);
}

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Drop an arXiv version suffix: `2606.02800v2` -> `2606.02800`. */
export function stripArxivVersion(arxivId: string): string {
  return arxivId.replace(/v\d+$/i, "");
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
  if (Math.abs(n) >= 100) return roundHalfUp(n, 0);
  if (Math.abs(n) >= 10) return roundHalfUp(n, 1);
  if (Math.abs(n) < 1) return roundHalfUp(n, 3);
  return roundHalfUp(n, 2);
}

// `toFixed` rounds the binary float, so 30.55 becomes "30.6" but 22.95 becomes
// "22.9". Shift the decimal point in the shortest decimal representation so ties
// round away from zero consistently.
function roundHalfUp(n: number, digits: number): string {
  const text = String(Math.abs(n));
  if (text.includes("e")) return n.toFixed(digits);
  const rounded = Number(`${Math.round(Number(`${text}e${digits}`))}e-${digits}`);
  return (n < 0 ? -rounded : rounded).toFixed(digits);
}

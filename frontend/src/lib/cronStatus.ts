import type { CronJobHealth } from "@/lib/api/operations";

/** Visual severity shared by the admin dashboards' status chips and cards. */
export type Tone = CronJobHealth;

export const toneClass = (tone: Tone): string => `cron-status--${tone}`;

export const formatUsd = (usd: number): string => `$${usd.toFixed(2)}`;

export const formatMicroUsd = (microusd: number): string => formatUsd(microusd / 1_000_000);

export function formatCronDate(dateString: string | null): string {
  if (!dateString) return "Never";
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return dateString;

  const diffMs = Date.now() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

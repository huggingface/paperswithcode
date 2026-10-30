import type { FrameworkPlatform } from "@/lib/api/catalog.types";

export const PLATFORM_LABELS: Record<FrameworkPlatform, string> = {
  gpu: "GPU",
  cpu: "CPU",
  apple: "Apple silicon",
};

/** GitHub star count, compact from 1,000 up (26414 → "26.4K"). */
export const formatStarCount = (stars: number) =>
  new Intl.NumberFormat("en", {
    notation: stars >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(stars);

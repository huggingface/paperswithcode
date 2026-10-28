import { paperQueryKeys } from "@/lib/paperQueryKeys";
/**
 * Shared visual components: tag/method chips, SOTA badges, inline icons,
 * paper thumbnails, and the PaperCard list item. `TagChip` takes a slug +
 * label; `PaperCard` takes the `PaperCardProps` shape produced by
 * `lib/transform.ts`.
 */

import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { AuthorAvatar } from "@/components/AuthorAvatar";
import LatexTitle, { LatexText } from "@/components/LatexTitle";
import { chipColors, hueFromSlug } from "@/lib/colors";
import type { Method } from "@/lib/api/catalog.types";
import { papersApi } from "@/lib/api/papers";
import type { PaperCardProps, SotaRank } from "@/lib/transform";
import { displayTaskName, humanizeSlug } from "@/lib/transform";
import { safeExternalHref } from "@/lib/safeExternalHref";

// ============================================================================
// Tag chip — backend slug → deterministic-hue pastel pill
// ============================================================================

interface TagChipProps {
  slug: string;
  label?: string;
  size?: "normal" | "small";
  onClick?: (slug: string) => void;
}

export const TagChip: React.FC<TagChipProps> = ({ slug, label, onClick }) => {
  const navigate = useNavigate();
  const hue = hueFromSlug(slug);
  const c = chipColors(hue);
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onClick) {
      onClick(slug);
      return;
    }
    navigate(`/tasks/${slug}`);
  };
  return (
    <span className="tag-chip" style={{ background: c.bg, color: c.text }} onClick={handleClick}>
      <span className="dot" style={{ background: c.dot }}></span>
      {displayTaskName(label || humanizeSlug(slug), slug)}
    </span>
  );
};

// ============================================================================
// Method chip — link to /methods/:slug
// ============================================================================

interface MethodChipProps {
  method: Pick<Method, "name"> & Partial<Pick<Method, "id" | "slug">>;
  onClick?: (slug: string) => void;
}

export const MethodChip: React.FC<MethodChipProps> = ({ method, onClick }) => {
  const navigate = useNavigate();
  const slug = method.slug || method.id || "";
  if (!slug) return null;
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onClick) {
      onClick(slug);
      return;
    }
    navigate(`/methods/${slug}`);
  };
  return (
    <span className="method-chip" onClick={handleClick}>
      {method.name}
    </span>
  );
};

// ============================================================================
// SOTA badges — a paper's top-3 leaderboard placements (SOTA / #2 / #3)
// ============================================================================

const SOTA_RANK_LABELS: Record<number, string> = { 1: "SOTA 🏆", 2: "#2", 3: "#3" };

interface SotaBadgesProps {
  ranks: SotaRank[];
  /** Paper detail href; the "+N more" suffix links to its results section. */
  paperHref: string;
  /** When set, render one truncated line per rank group (SOTA / #2 / #3),
   *  stacked vertically. Used on the paper page. Cards keep a single line. */
  wrap?: boolean;
}

/** One benchmark placement, annotated for single-line rendering + measurement. */
interface SotaUnit {
  name: string;
  href: string | null;
  rank: number;
  /** First benchmark of its rank group (gets the "· #N on" prefix). */
  isGroupStart: boolean;
  /** Text rendered before+including this name, used for width measurement so
   *  it matches the laid-out line exactly. */
  measureText: string;
}

/** A single truncated line of placements: fits as many units as the width
 *  allows, collapsing the overflow into a "· +N more" link to #results. */
const SotaLine: React.FC<{ units: SotaUnit[]; paperHref: string }> = ({ units, paperHref }) => {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const measureRef = React.useRef<HTMLSpanElement>(null);
  const [visibleCount, setVisibleCount] = React.useState(units.length);

  React.useLayoutEffect(() => {
    const container = containerRef.current;
    const measure = measureRef.current;
    if (!container || !measure || units.length === 0) return;

    const widthOf = (text: string) => {
      measure.textContent = text;
      return measure.scrollWidth;
    };

    const compute = () => {
      const avail = container.clientWidth;
      if (avail <= 0) return;

      let used = 0;
      let kept = 0;
      for (const unit of units) {
        const w = widthOf(unit.measureText);
        if (used + w <= avail) {
          used += w;
          kept += 1;
        } else {
          break;
        }
      }

      // Reserve room for the "· +N more" suffix, shrinking until it fits.
      if (kept < units.length) {
        while (kept > 0 && used + widthOf(` · +${units.length - kept} more`) > avail) {
          kept -= 1;
          used -= widthOf(units[kept].measureText);
        }
        // Always show at least one benchmark; CSS clips any overflow.
        if (kept === 0) kept = 1;
      }

      setVisibleCount(kept);
    };

    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(container);
    return () => ro.disconnect();
  }, [units]);

  if (units.length === 0) return null;

  const shown = units.slice(0, Math.max(1, Math.min(visibleCount, units.length)));
  const moreCount = units.length - shown.length;

  return (
    <div className="paper-sota" ref={containerRef}>
      <span ref={measureRef} className="paper-sota-measure" aria-hidden="true" />
      {shown.map((u, i) => (
        <React.Fragment key={`${u.href || u.name}-${i}`}>
          {u.isGroupStart ? (
            <>
              {i > 0 && <span className="paper-sota-sep"> · </span>}
              <span
                className={`paper-sota-label${u.rank === 1 ? " paper-sota-label--sota" : ""}`}
              >
                {SOTA_RANK_LABELS[u.rank]}
              </span>
              <span className="paper-sota-on"> on </span>
            </>
          ) : (
            <span className="paper-sota-sep">, </span>
          )}
          {u.href ? (
            <Link
              to={u.href}
              className="paper-sota-name"
              onClick={(e) => e.stopPropagation()}
            >
              {u.name}
            </Link>
          ) : (
            <span className="paper-sota-name">{u.name}</span>
          )}
        </React.Fragment>
      ))}
      {moreCount > 0 && (
        <Link
          to={`${paperHref}#results`}
          className="paper-sota-more"
          onClick={(e) => e.stopPropagation()}
        >
          {" · +"}
          {moreCount} more
        </Link>
      )}
    </div>
  );
};

export const SotaBadges: React.FC<SotaBadgesProps> = ({ ranks, paperHref, wrap = false }) => {
  // Cards: all groups packed onto one line, separated by " · ". The first unit
  // of a group after the first carries the "· #N on" prefix.
  const combinedUnits = React.useMemo<SotaUnit[]>(() => {
    const result: SotaUnit[] = [];
    let firstGroup = true;
    for (const rank of [1, 2, 3]) {
      const items = ranks.filter((r) => r.rank === rank);
      items.forEach((b, idx) => {
        const isGroupStart = idx === 0;
        const prefix = isGroupStart
          ? `${firstGroup ? "" : " · "}${SOTA_RANK_LABELS[rank]} on `
          : ", ";
        result.push({
          name: b.name,
          href: b.href,
          rank,
          isGroupStart,
          measureText: prefix + b.name,
        });
      });
      if (items.length > 0) firstGroup = false;
    }
    return result;
  }, [ranks]);

  // Paper page: one line per rank group. Each group starts fresh (no leading
  // " · "), so its first unit measures "SOTA 🏆 on <name>".
  const groupedUnits = React.useMemo<SotaUnit[][]>(() => {
    return [1, 2, 3]
      .map((rank) => {
        const items = ranks.filter((r) => r.rank === rank);
        return items.map((b, idx) => ({
          name: b.name,
          href: b.href,
          rank,
          isGroupStart: idx === 0,
          measureText: (idx === 0 ? `${SOTA_RANK_LABELS[rank]} on ` : ", ") + b.name,
        }));
      })
      .filter((group) => group.length > 0);
  }, [ranks]);

  if (wrap) {
    if (groupedUnits.length === 0) return null;
    return (
      <div className="paper-sota-stack">
        {groupedUnits.map((group) => (
          <SotaLine key={group[0].rank} units={group} paperHref={paperHref} />
        ))}
      </div>
    );
  }

  if (combinedUnits.length === 0) return null;
  return <SotaLine units={combinedUnits} paperHref={paperHref} />;
};

// ============================================================================
// Inline icons (size-restricted SVG paths)
// ============================================================================

interface IconProps {
  name:
    | "search"
    | "arrowUp"
    | "arrowLeft"
    | "arrowRight"
    | "external"
    | "github"
    | "citation"
    | "bookmark"
    | "chart"
    | "chat"
    | "pdf"
    | "copy"
    | "sparkle"
    | "user"
    | "globe"
    | "menu"
    | "close"
    | "pencil";
  size?: number;
}

export const Icon: React.FC<IconProps> = ({ name, size = 14 }) => {
  const paths: Record<IconProps["name"], React.ReactNode> = {
    search: <path d="M11 11l3 3M7 12.5a5.5 5.5 0 110-11 5.5 5.5 0 010 11z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />,
    arrowUp: <path d="M8 3l5 6H3l5-6z" fill="currentColor" />,
    arrowLeft: <path d="M9 3l-4 5 4 5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
    arrowRight: <path d="M7 3l4 5-4 5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
    external: <path d="M5 3h-2v8h8v-2M9 3h3v3M7 9l5-5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
    github: <path d="M8 1a7 7 0 00-2.21 13.64c.35.06.48-.15.48-.34v-1.2c-1.95.42-2.36-.94-2.36-.94-.32-.81-.78-1.03-.78-1.03-.64-.43.05-.43.05-.43.7.05 1.07.72 1.07.72.62 1.07 1.64.76 2.04.58.06-.45.24-.76.44-.94-1.55-.18-3.18-.78-3.18-3.46 0-.76.27-1.39.72-1.88-.07-.18-.31-.89.07-1.86 0 0 .59-.19 1.92.72.56-.15 1.16-.23 1.75-.24.59 0 1.19.08 1.75.24 1.33-.9 1.92-.72 1.92-.72.38.97.14 1.68.07 1.86.45.49.72 1.12.72 1.88 0 2.69-1.64 3.28-3.19 3.45.25.22.48.65.48 1.32v1.95c0 .19.13.41.49.34A7 7 0 008 1z" fill="currentColor" />,
    citation: <path d="M3 4h3v3H3zM4 7v1.5a1.5 1.5 0 01-1.5 1.5M9 4h3v3H9zM10 7v1.5a1.5 1.5 0 01-1.5 1.5" stroke="currentColor" strokeWidth="1.2" fill="none" />,
    bookmark: <path d="M4 2h8v12l-4-3-4 3V2z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round" />,
    chart: <path d="M2 13h12M3 11l3-4 3 2 4-5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
    chat: <path d="M3 3h10v7H7l-3 3v-3H3V3z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round" />,
    pdf: <path d="M5 2h5l3 3v9H5V2z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round" />,
    copy: <path d="M5 5h7v8H5V5zM3 3h7v2M3 3v8h2" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinejoin="round" />,
    sparkle: <path d="M8 2l1.2 3.8L13 7l-3.8 1.2L8 12l-1.2-3.8L3 7l3.8-1.2L8 2z" fill="currentColor" />,
    user: <path d="M8 8a3 3 0 100-6 3 3 0 000 6zM2 14c0-3 2.5-5 6-5s6 2 6 5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />,
    globe: <path d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM1.5 8h13M8 1.5c1.7 1.9 2.6 4.2 2.6 6.5s-.9 4.6-2.6 6.5M8 1.5C6.3 3.4 5.4 5.7 5.4 8s.9 4.6 2.6 6.5" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" />,
    menu: <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />,
    close: <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />,
    pencil: <path d="M10.5 2.5l3 3L6 13H3v-3l7.5-7.5zM9 4l3 3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
  };
  return (
    <svg className={size === 11 ? "icon-sm" : "icon"} viewBox="0 0 16 16" width={size} height={size}>
      {paths[name]}
    </svg>
  );
};

// Official multi-color Hugging Face logo. Kept as a standalone component
// because the shared `Icon` renders single-color `currentColor` paths, while
// the HF mark needs its brand palette to stay recognizable on the feed cards.
const HuggingFaceLogo: React.FC<{ size?: number }> = ({ size = 16 }) => (
  <svg
    className="hf-logo"
    width={size}
    height={size}
    viewBox="0 0 95 88"
    fill="none"
    aria-hidden="true"
    focusable="false"
  >
    <path fill="#FFD21E" d="M47.21 76.5a34.75 34.75 0 1 0 0-69.5 34.75 34.75 0 0 0 0 69.5Z" />
    <path fill="#FF9D0B" d="M81.96 41.75a34.75 34.75 0 1 0-69.5 0 34.75 34.75 0 0 0 69.5 0Zm-73.5 0a38.75 38.75 0 1 1 77.5 0 38.75 38.75 0 0 1-77.5 0Z" />
    <path fill="#3A3B45" d="M58.5 32.3c1.28.44 1.78 3.06 3.07 2.38a5 5 0 1 0-6.76-2.07c.61 1.15 2.55-.72 3.7-.32ZM34.95 32.3c-1.28.44-1.79 3.06-3.07 2.38a5 5 0 1 1 6.76-2.07c-.61 1.15-2.56-.72-3.7-.32Z" />
    <path fill="#FF323D" d="M46.96 56.29c9.83 0 13-8.76 13-13.26 0-2.34-1.57-1.6-4.09-.36-2.33 1.15-5.46 2.74-8.9 2.74-7.19 0-13-6.88-13-2.38s3.16 13.26 13 13.26Z" />
    <path fill="#3A3B45" fillRule="evenodd" clipRule="evenodd" d="M39.43 54a8.7 8.7 0 0 1 5.3-4.49c.4-.12.81.57 1.24 1.28.4.68.82 1.37 1.24 1.37.45 0 .9-.68 1.33-1.35.45-.7.89-1.38 1.32-1.25a8.61 8.61 0 0 1 5 4.17c3.73-2.94 5.1-7.74 5.1-10.7 0-2.34-1.57-1.6-4.09-.36l-.14.07c-2.31 1.15-5.39 2.67-8.77 2.67s-6.45-1.52-8.77-2.67c-2.6-1.29-4.23-2.1-4.23.29 0 3.05 1.46 8.06 5.47 10.97Z" />
    <path fill="#FF9D0B" d="M70.71 37a3.25 3.25 0 1 0 0-6.5 3.25 3.25 0 0 0 0 6.5ZM24.21 37a3.25 3.25 0 1 0 0-6.5 3.25 3.25 0 0 0 0 6.5ZM17.52 48c-1.62 0-3.06.66-4.07 1.87a5.97 5.97 0 0 0-1.33 3.76 7.1 7.1 0 0 0-1.94-.3c-1.55 0-2.95.59-3.94 1.66a5.8 5.8 0 0 0-.8 7 5.3 5.3 0 0 0-1.79 2.82c-.24.9-.48 2.8.8 4.74a5.22 5.22 0 0 0-.37 5.02c1.02 2.32 3.57 4.14 8.52 6.1 3.07 1.22 5.89 2 5.91 2.01a44.33 44.33 0 0 0 10.93 1.6c5.86 0 10.05-1.8 12.46-5.34 3.88-5.69 3.33-10.9-1.7-15.92-2.77-2.78-4.62-6.87-5-7.77-.78-2.66-2.84-5.62-6.25-5.62a5.7 5.7 0 0 0-4.6 2.46c-1-1.26-1.98-2.25-2.86-2.82A7.4 7.4 0 0 0 17.52 48Zm0 4c.51 0 1.14.22 1.82.65 2.14 1.36 6.25 8.43 7.76 11.18.5.92 1.37 1.31 2.14 1.31 1.55 0 2.75-1.53.15-3.48-3.92-2.93-2.55-7.72-.68-8.01.08-.02.17-.02.24-.02 1.7 0 2.45 2.93 2.45 2.93s2.2 5.52 5.98 9.3c3.77 3.77 3.97 6.8 1.22 10.83-1.88 2.75-5.47 3.58-9.16 3.58-3.81 0-7.73-.9-9.92-1.46-.11-.03-13.45-3.8-11.76-7 .28-.54.75-.76 1.34-.76 2.38 0 6.7 3.54 8.57 3.54.41 0 .7-.17.83-.6.79-2.85-12.06-4.05-10.98-8.17.2-.73.71-1.02 1.44-1.02 3.14 0 10.2 5.53 11.68 5.53.11 0 .2-.03.24-.1.74-1.2.33-2.04-4.9-5.2-5.21-3.16-8.88-5.06-6.8-7.33.24-.26.58-.38 1-.38 3.17 0 10.66 6.82 10.66 6.82s2.02 2.1 3.25 2.1c.28 0 .52-.1.68-.38.86-1.46-8.06-8.22-8.56-11.01-.34-1.9.24-2.85 1.31-2.85Z" />
    <path fill="#FFD21E" d="M38.6 76.69c2.75-4.04 2.55-7.07-1.22-10.84-3.78-3.77-5.98-9.3-5.98-9.3s-.82-3.2-2.69-2.9c-1.87.3-3.24 5.08.68 8.01 3.91 2.93-.78 4.92-2.29 2.17-1.5-2.75-5.62-9.82-7.76-11.18-2.13-1.35-3.63-.6-3.13 2.2.5 2.79 9.43 9.55 8.56 11-.87 1.47-3.93-1.71-3.93-1.71s-9.57-8.71-11.66-6.44c-2.08 2.27 1.59 4.17 6.8 7.33 5.23 3.16 5.64 4 4.9 5.2-.75 1.2-12.28-8.53-13.36-4.4-1.08 4.11 11.77 5.3 10.98 8.15-.8 2.85-9.06-5.38-10.74-2.18-1.7 3.21 11.65 6.98 11.76 7.01 4.3 1.12 15.25 3.49 19.08-2.12Z" />
    <path fill="#FF9D0B" d="M77.4 48c1.62 0 3.07.66 4.07 1.87a5.97 5.97 0 0 1 1.33 3.76 7.1 7.1 0 0 1 1.95-.3c1.55 0 2.95.59 3.94 1.66a5.8 5.8 0 0 1 .8 7 5.3 5.3 0 0 1 1.78 2.82c.24.9.48 2.8-.8 4.74a5.22 5.22 0 0 1 .37 5.02c-1.02 2.32-3.57 4.14-8.51 6.1-3.08 1.22-5.9 2-5.92 2.01a44.33 44.33 0 0 1-10.93 1.6c-5.86 0-10.05-1.8-12.46-5.34-3.88-5.69-3.33-10.9 1.7-15.92 2.78-2.78 4.63-6.87 5.01-7.77.78-2.66 2.83-5.62 6.24-5.62a5.7 5.7 0 0 1 4.6 2.46c1-1.26 1.98-2.25 2.87-2.82A7.4 7.4 0 0 1 77.4 48Zm0 4c-.51 0-1.13.22-1.82.65-2.13 1.36-6.25 8.43-7.76 11.18a2.43 2.43 0 0 1-2.14 1.31c-1.54 0-2.75-1.53-.14-3.48 3.91-2.93 2.54-7.72.67-8.01a1.54 1.54 0 0 0-.24-.02c-1.7 0-2.45 2.93-2.45 2.93s-2.2 5.52-5.97 9.3c-3.78 3.77-3.98 6.8-1.22 10.83 1.87 2.75 5.47 3.58 9.15 3.58 3.82 0 7.73-.9 9.93-1.46.1-.03 13.45-3.8 11.76-7-.29-.54-.75-.76-1.34-.76-2.38 0-6.71 3.54-8.57 3.54-.42 0-.71-.17-.83-.6-.8-2.85 12.05-4.05 10.97-8.17-.19-.73-.7-1.02-1.44-1.02-3.14 0-10.2 5.53-11.68 5.53-.1 0-.19-.03-.23-.1-.74-1.2-.34-2.04 4.88-5.2 5.23-3.16 8.9-5.06 6.8-7.33-.23-.26-.57-.38-.98-.38-3.18 0-10.67 6.82-10.67 6.82s-2.02 2.1-3.24 2.1a.74.74 0 0 1-.68-.38c-.87-1.46 8.05-8.22 8.55-11.01.34-1.9-.24-2.85-1.31-2.85Z" />
    <path fill="#FFD21E" d="M56.33 76.69c-2.75-4.04-2.56-7.07 1.22-10.84 3.77-3.77 5.97-9.3 5.97-9.3s.82-3.2 2.7-2.9c1.86.3 3.23 5.08-.68 8.01-3.92 2.93.78 4.92 2.28 2.17 1.51-2.75 5.63-9.82 7.76-11.18 2.13-1.35 3.64-.6 3.13 2.2-.5 2.79-9.42 9.55-8.55 11 .86 1.47 3.92-1.71 3.92-1.71s9.58-8.71 11.66-6.44c2.08 2.27-1.58 4.17-6.8 7.33-5.23 3.16-5.63 4-4.9 5.2.75 1.2 12.28-8.53 13.36-4.4 1.08 4.11-11.76 5.3-10.97 8.15.8 2.85 9.05-5.38 10.74-2.18 1.69 3.21-11.65 6.98-11.76 7.01-4.31 1.12-15.26 3.49-19.08-2.12Z" />
  </svg>
);

// ============================================================================
// Hand-drawn PDF preview (fallback when no real thumbnail exists)
// ============================================================================

const seedRand = (seed: string): (() => number) => {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  }
  return () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    h ^= h >>> 16;
    return ((h >>> 0) % 10000) / 10000;
  };
};

const PdfThumbnail: React.FC<{ paperId: string }> = ({ paperId }) => {
  const rand = seedRand(paperId);
  const W = 160;
  const H = 220;
  const titleLines = [0.85 + rand() * 0.1, 0.55 + rand() * 0.25];
  const authorW = 0.45 + rand() * 0.3;
  const colLines: number[] = [];
  const numLines = 9 + Math.floor(rand() * 3);
  for (let i = 0; i < numLines; i++) colLines.push(0.55 + rand() * 0.4);
  const hasFigure = rand() > 0.3;
  const figureType = Math.floor(rand() * 3);
  const rightLines: number[] = [];
  const rightCount = 6 + Math.floor(rand() * 3);
  for (let i = 0; i < rightCount; i++) rightLines.push(0.5 + rand() * 0.45);

  const lineColor = "#9A9588";
  const titleColor = "#3A352D";
  const padding = 5;
  const colWidth = (W - padding * 2 - 2) / 2;
  const colLeft = padding;
  const colRight = padding + colWidth + 2;

  let y = padding + 2;
  const titleY = y;
  y += 4 + 2;
  const authorsY = y + 1;
  y += 5;
  const stampY = y;
  y += 3;
  const bodyTop = y + 1;

  return (
    <div
      style={{
        width: W,
        height: H,
        background: "#FDFCF9",
        border: "1px solid var(--hairline-strong)",
        borderRadius: 2,
        boxShadow: "0 1px 0 rgba(0,0,0,0.04), 0 4px 8px -4px rgba(0,0,0,0.08)",
        flexShrink: 0,
        overflow: "hidden",
        position: "relative",
      }}
    >
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
        {titleLines.map((w, i) => (
          <rect
            key={`t${i}`}
            x={padding + ((W - padding * 2) * (1 - w)) / 2}
            y={titleY + i * 2.4}
            width={(W - padding * 2) * w}
            height={1.4}
            fill={titleColor}
            rx={0.3}
          />
        ))}
        <rect
          x={padding + ((W - padding * 2) * (1 - authorW)) / 2}
          y={authorsY}
          width={(W - padding * 2) * authorW}
          height={0.9}
          fill={lineColor}
          opacity={0.7}
          rx={0.2}
        />
        <rect x={padding} y={stampY} width={6} height={1} fill={titleColor} opacity={0.6} />
        {colLines.map((w, i) => {
          const ly = bodyTop + i * 2.1;
          if (ly > H - padding - 1) return null;
          return (
            <rect
              key={`l${i}`}
              x={colLeft}
              y={ly}
              width={colWidth * w}
              height={0.8}
              fill={lineColor}
              opacity={0.55}
              rx={0.2}
            />
          );
        })}
        {hasFigure && (
          <g>
            <rect
              x={colRight}
              y={bodyTop}
              width={colWidth}
              height={14}
              fill="#F0EBE0"
              stroke={lineColor}
              strokeWidth={0.3}
              opacity={0.9}
            />
            {figureType === 0 && (
              <g stroke={titleColor} strokeWidth={0.4} fill="none" opacity={0.6}>
                <polyline
                  points={`${colRight + 2},${bodyTop + 11} ${colRight + 6},${bodyTop + 8} ${colRight + 10},${bodyTop + 9} ${colRight + 14},${bodyTop + 5} ${colRight + 18},${bodyTop + 6} ${colRight + 22},${bodyTop + 3}`}
                />
              </g>
            )}
            {figureType === 1 && (
              <g opacity={0.55}>
                <circle cx={colRight + colWidth / 2} cy={bodyTop + 7} r={3.5} fill={titleColor} />
                <rect x={colRight + 2} y={bodyTop + 11} width={colWidth - 4} height={1.5} fill={lineColor} />
              </g>
            )}
            {figureType === 2 && (
              <g opacity={0.55}>
                <rect x={colRight + 3} y={bodyTop + 5} width={colWidth - 6} height={1} fill={titleColor} />
                <rect x={colRight + 6} y={bodyTop + 8} width={colWidth - 12} height={0.8} fill={titleColor} />
              </g>
            )}
          </g>
        )}
        {rightLines.map((w, i) => {
          const ly = bodyTop + (hasFigure ? 16 : 0) + i * 2.1;
          if (ly > H - padding - 1) return null;
          return (
            <rect
              key={`r${i}`}
              x={colRight}
              y={ly}
              width={colWidth * w}
              height={0.8}
              fill={lineColor}
              opacity={0.55}
              rx={0.2}
            />
          );
        })}
      </svg>
    </div>
  );
};

/**
 * Real paper thumbnail wrapper. Prefers the backend-supplied thumbnail_url;
 * falls back to the hand-drawn PdfThumbnail when no image is available.
 */
export const PaperPreview: React.FC<{ paperId: string; title: string; thumbnailUrl: string | null; priority?: boolean }> = ({
  paperId,
  title,
  thumbnailUrl,
  priority = false,
}) => {
  const [errored, setErrored] = React.useState(false);
  const [imgAttempt, setImgAttempt] = React.useState(0);
  const [shouldLoad, setShouldLoad] = React.useState(priority);
  const containerRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    setErrored(false);
    setImgAttempt(0);
  }, [thumbnailUrl]);

  const resolvedThumbnailUrl = React.useMemo(() => {
    if (!thumbnailUrl) return null;
    if (imgAttempt === 0) return thumbnailUrl;
    const separator = thumbnailUrl.includes("?") ? "&" : "?";
    return `${thumbnailUrl}${separator}retry=${imgAttempt}`;
  }, [thumbnailUrl, imgAttempt]);

  React.useEffect(() => {
    if (priority || shouldLoad) return;
    const node = containerRef.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShouldLoad(true);
          observer.disconnect();
        }
      },
      { rootMargin: "250px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [priority, shouldLoad]);

  if (thumbnailUrl && !errored) {
    return (
      <div
        ref={containerRef}
        style={{
          width: 160,
          height: 220,
          background: "#FDFCF9",
          border: "1px solid var(--hairline-strong)",
          borderRadius: 2,
          boxShadow: "0 1px 0 rgba(0,0,0,0.04), 0 4px 8px -4px rgba(0,0,0,0.08)",
          flexShrink: 0,
          overflow: "hidden",
          position: "relative",
        }}
      >
        {(priority || shouldLoad) && resolvedThumbnailUrl && (
          <img
            key={resolvedThumbnailUrl}
            src={resolvedThumbnailUrl}
            alt={`Thumbnail for ${title}`}
            loading={priority ? "eager" : "lazy"}
            decoding="async"
            fetchPriority={priority ? "high" : "auto"}
            style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
            onError={() => {
              if (imgAttempt < 1) {
                setImgAttempt((n) => n + 1);
                return;
              }
              setErrored(true);
            }}
          />
        )}
      </div>
    );
  }
  return <PdfThumbnail paperId={paperId} />;
};

// ============================================================================
// Paper card — list item used by FeedView, TagBrowseView, MethodDetailView
// ============================================================================

interface PaperCardComponentProps {
  paper: PaperCardProps;
  rank?: number | null;
  showInstitution?: boolean;
  onClickTag?: (slug: string) => void;
  highlightQuery?: string;
  /** Names of the followed entities that put this paper on the Following feed. */
  followReasons?: string[];
}

// "Agents", "Agents and Reasoning", "Agents, Reasoning and 2 more"
function formatFollowReasons(reasons: string[]): string {
  const names = [...new Set(reasons.map((r) => r.replace(/ \(subtask\)$/, "")))];
  const shown = names.length > 3 ? [...names.slice(0, 2), `${names.length - 2} more`] : names;
  return shown.length > 1 ? `${shown.slice(0, -1).join(", ")} and ${shown[shown.length - 1]}` : shown[0];
}

const LANGUAGE_MODELING_TASK_SLUG = "language-modeling";

// The "Large Language Model" method is redundant on a feed card whenever the
// paper already carries the "language-modeling" task tag, so we drop just that
// one method chip there. Match on a normalized slug/name so variants like
// `large-language-model-llm` / "Large language model (LLM)" are all caught.
function normalizeLlmKey(value: string | undefined): string {
  if (!value) return "";
  return value
    .toLowerCase()
    .replace(/\(.*?\)/g, " ") // drop parenthetical aliases, e.g. "(LLM)"
    .replace(/[^a-z]+/g, " ") // collapse punctuation/hyphens to spaces
    .replace(/\bllm\b/g, " ") // drop the "llm" alias token (e.g. slug suffix)
    .replace(/\s+/g, " ")
    .trim()
    .replace(/s$/, ""); // singular/plural
}

function isLargeLanguageModelMethod(method: PaperCardProps["methods"][number]): boolean {
  return (
    normalizeLlmKey(method.slug) === "large language model" ||
    normalizeLlmKey(method.name) === "large language model"
  );
}

function visibleFeedMethods(paper: PaperCardProps): PaperCardProps["methods"] {
  if (!paper.tags.includes(LANGUAGE_MODELING_TASK_SLUG)) {
    return paper.methods;
  }
  return paper.methods.filter((m) => !isLargeLanguageModelMethod(m));
}

const PaperOrganizationLogo: React.FC<
  PaperCardProps["organizations"][number]
> = ({ name, slug, logoUrl }) => {
  const [failed, setFailed] = React.useState(false);
  if (!logoUrl || failed) return null;

  return (
    <Link
      to={`/orgs/${slug}`}
      className="paper-organization-logo"
      aria-label={`View ${name} organization`}
      title={name}
    >
      <img src={logoUrl} alt="" onError={() => setFailed(true)} />
    </Link>
  );
};

export const PaperCard: React.FC<PaperCardComponentProps> = ({
  paper,
  rank,
  showInstitution = true,
  onClickTag,
  highlightQuery,
  followReasons,
}) => {
  const queryClient = useQueryClient();
  const paperHref = `/paper/${paper.id}`;
  const prefetchPaper = React.useCallback(() => {
    queryClient.prefetchQuery({
      queryKey: paperQueryKeys.detail(paper.id),
      queryFn: () => papersApi.get(paper.id, true),
      staleTime: 10 * 60 * 1000,
    });
  }, [paper.id, queryClient]);
  const visibleAuthors = paper.authors.slice(0, 3).map((name, index) => {
    const authorId = paper.authorIds?.[index];
    const hfProfile = paper.authorHfProfiles?.[index];
    return (
      <React.Fragment key={index}>
        {index > 0 && ", "}
        {hfProfile && (
          <AuthorAvatar className="paper-card-author-avatar" url={hfProfile.avatarUrl} />
        )}
        {authorId ? <Link to={`/authors/${authorId}`}>{name}</Link> : name}
      </React.Fragment>
    );
  });
  const totalAuthors = paper.authors.length;
  const visibleMethods = visibleFeedMethods(paper);
  return (
    <article className="paper-card">
      {rank != null && (
        <Link
          to={paperHref}
          className="paper-thumb-wrap"
          onFocus={prefetchPaper}
          onMouseEnter={prefetchPaper}
        >
          <PaperPreview paperId={paper.id} title={paper.title} thumbnailUrl={paper.thumbnailUrl} priority={rank <= 3} />
        </Link>
      )}
      <div className="paper-body">
        <div className="paper-body-main">
          {followReasons && followReasons.length > 0 && (
            <div className="paper-follow-reason">
              Because you follow {formatFollowReasons(followReasons)}
            </div>
          )}
          <h3 className="paper-title">
            <Link to={paperHref} onFocus={prefetchPaper} onMouseEnter={prefetchPaper}>
              <LatexTitle title={paper.title} highlight={highlightQuery} />
            </Link>
            {showInstitution && paper.organizations.length > 0 && (
              <span className="paper-organization-logos">
                {paper.organizations.map((organization) => (
                  <PaperOrganizationLogo key={organization.slug} {...organization} />
                ))}
              </span>
            )}
          </h3>
          <div className="paper-authors">
            {visibleAuthors}
            {totalAuthors > 3 && (
              <span>
                {", "}+{totalAuthors - 3} authors
              </span>
            )}
            {paper.date && (
              <>
                {totalAuthors > 0 ? " · " : ""}
                <span>{paper.date}</span>
              </>
            )}
            {paper.citations > 0 && (
              <>
                {totalAuthors > 0 || paper.date ? " · " : ""}
                <span>{paper.citations.toLocaleString()} citations</span>
              </>
            )}
          </div>
          {paper.abstract && (
            <p className="paper-abstract">
              <LatexText text={paper.abstract} highlight={highlightQuery} />
            </p>
          )}
          {paper.sotaRanks.length > 0 && <SotaBadges ranks={paper.sotaRanks} paperHref={paperHref} />}
          {(paper.tags.length > 0 || visibleMethods.length > 0) && (
            <div className="paper-tags paper-tags--clamped">
              {paper.tags.map((slug) => (
                <TagChip key={slug} slug={slug} onClick={onClickTag} />
              ))}
              {visibleMethods.map((m) => (
                <MethodChip key={m.id || m.slug || m.name} method={m} />
              ))}
            </div>
          )}
        </div>
        {(paper.githubUrl || paper.hfUrl) && (
          <div className="paper-resources">
            {safeExternalHref(paper.githubUrl) && (
              <a
                className="paper-resource is-link"
                href={safeExternalHref(paper.githubUrl) ?? undefined}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Open GitHub repository"
                onClick={(e) => e.stopPropagation()}
              >
                <Icon name="github" size={20} />
                {paper.velocity24h != null && paper.velocity24h > 0 && (
                  <span className="resource-stat">
                    <span className="resource-value">
                      <span className="gh-rate-arrow">↑</span>
                      {formatStarsPerHour(paper.velocity24h)}
                    </span>
                    <span className="resource-label">stars / hr</span>
                  </span>
                )}
              </a>
            )}
            {safeExternalHref(paper.hfUrl) && paper.hfKind && (
              <a
                className="paper-resource is-link"
                href={safeExternalHref(paper.hfUrl) ?? undefined}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Open Hugging Face ${paper.hfKind}`}
                onClick={(e) => e.stopPropagation()}
              >
                <HuggingFaceLogo size={20} />
                <span className="resource-stat">
                  <span className="resource-value">{paper.hfCount}</span>
                  <span className="resource-label">{paper.hfKind}</span>
                </span>
              </a>
            )}
          </div>
        )}
      </div>
    </article>
  );
};

function formatStarsPerHour(n: number): string {
  return n.toFixed(1);
}

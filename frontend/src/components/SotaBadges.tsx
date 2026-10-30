import React from "react";
import { Link } from "react-router-dom";

import type { SotaRank } from "@/lib/transform";

// SOTA badges — a paper's top-3 leaderboard placements (SOTA / #2 / #3)

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

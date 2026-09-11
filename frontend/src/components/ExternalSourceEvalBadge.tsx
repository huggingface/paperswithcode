/**
 * Inline "external" badge shown when a score came from an independent source
 * rather than the evaluated paper/model's own release materials.
 */

import React from "react";
import { Link } from "react-router-dom";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import "@/styles/evaluation-badges.css";
import { safeExternalHref } from "@/lib/safeExternalHref";

type Props = {
  sourceUrl?: string | null;
};

function sourceLabel(sourceUrl?: string | null): string {
  if (!sourceUrl) return "Evaluation sourced outside this paper";
  const lower = sourceUrl.toLowerCase();
  if (lower.includes("open-asr-leaderboard")) return "Open ASR Leaderboard";
  if (lower.includes("arcprize.org")) return "ARC Prize Leaderboard";
  if (lower.includes("frontierswe.com")) return "FrontierSWE";
  if (lower.includes("deepswe.datacurve.ai")) return "DeepSWE";
  try {
    const parsed = new URL(sourceUrl, "https://paperswithcode.co");
    if (parsed.pathname.startsWith("/paper/")) return "Source paper";
    return parsed.hostname.replace(/^www\./, "");
  } catch {
    return sourceUrl;
  }
}

const ExternalSourceEvalBadge: React.FC<Props> = ({ sourceUrl }) => {
  const safeSourceUrl = safeExternalHref(sourceUrl);
  const internalPaperUrl =
    typeof sourceUrl === "string" && sourceUrl.startsWith("/paper/")
      ? sourceUrl
      : null;
  const label = sourceLabel(sourceUrl);
  return (
    <HoverCard openDelay={120} closeDelay={120}>
      <HoverCardTrigger asChild>
        <button
          type="button"
          className="bm-external-source-tag"
          aria-label={`Externally sourced evaluation: ${label}`}
        >
          External
        </button>
      </HoverCardTrigger>
      <HoverCardContent
        side="top"
        align="start"
        className="w-auto max-w-[280px] p-3 text-sm leading-snug"
      >
        This score was sourced outside this paper.
        {internalPaperUrl ? (
          <>
            {" "}
            <Link
              to={internalPaperUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="external-eval-tooltip-link"
            >
              {label}
            </Link>
            .
          </>
        ) : safeSourceUrl ? (
          <>
            {" "}
            <a
              href={safeSourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="external-eval-tooltip-link"
            >
              {label}
            </a>
            .
          </>
        ) : (
          <> {label}.</>
        )}
      </HoverCardContent>
    </HoverCard>
  );
};

export default ExternalSourceEvalBadge;

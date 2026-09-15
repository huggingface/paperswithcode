/**
 * Inline "closed" badge shown next to evaluations of closed-source models on
 * benchmark leaderboards and paper result tables.
 *
 * Hovering (or focusing) the badge reveals a small card explaining what it
 * means and links to `/settings`, where users can opt out of seeing these
 * rows. We use a HoverCard rather than a Tooltip: the content is interactive
 * (it contains a link), and HoverCard's built-in open/close delays keep the
 * popup stable instead of flickering as the pointer moves between the tiny
 * trigger and the card.
 */

import React from "react";
import { Link } from "react-router-dom";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import "@/styles/evaluation-badges.css";

const ClosedSourceEvalBadge: React.FC = () => (
  <HoverCard openDelay={120} closeDelay={120}>
    <HoverCardTrigger asChild>
      <button
        type="button"
        className="bm-closed-source-tag"
        aria-label="Closed-source model"
      >
        closed
      </button>
    </HoverCardTrigger>
    <HoverCardContent
      side="top"
      align="start"
      className="w-auto max-w-[260px] p-3 text-sm leading-snug"
    >
      This is an evaluation of a closed-source model. You can disable viewing
      these in your{" "}
      <Link to="/settings" className="closed-eval-tooltip-link">
        settings
      </Link>
      .
    </HoverCardContent>
  </HoverCard>
);

export default ClosedSourceEvalBadge;

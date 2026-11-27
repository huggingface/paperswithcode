import React from "react";
import { Link } from "react-router-dom";
import { Icon } from "./Icon";

/** Links a paper's position in the default trending feed back to that feed. */
export const PaperTrendingPill: React.FC<{ rank: number }> = ({ rank }) => (
  <Link
    to="/"
    className="detail-trending-pill"
    title={`Ranked #${rank} of papers published in the last 7 days, by GitHub, Hugging Face and X momentum`}
  >
    <Icon name="chart" size={11} />
    #{rank} in trending this week
  </Link>
);

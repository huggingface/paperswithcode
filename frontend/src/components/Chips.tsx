import React from "react";
import { useNavigate } from "react-router-dom";

import type { Method } from "@/lib/api/catalog.types";
import { chipColors, hueFromSlug } from "@/lib/colors";
import { displayTaskName, humanizeSlug } from "@/lib/transform";

// Tag chip — backend slug → deterministic-hue pastel pill

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

// Method chip — link to /methods/:slug

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

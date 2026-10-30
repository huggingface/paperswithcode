/**
 * Action-row button on the paper detail page that toggles the user's bookmark
 * for the current paper.
 *
 * - Reads bookmark state from `useBookmarkIds()` (cheap shared cache).
 * - Toggling calls `useToggleBookmark()` which optimistically updates that
 *   cache. If the user is signed out, the hook redirects to the HF OAuth
 *   login flow with `return_to=current path`.
 */

import React from "react";

import { Icon } from "@/components/Icon";
import { isAuthDisabled } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";
import { useBookmarkIds, useToggleBookmark } from "@/hooks/useBookmarks";

interface SavePaperButtonProps {
  paperId: string;
}

export const SavePaperButton: React.FC<SavePaperButtonProps> = ({ paperId }) => {
  const { user } = useAuth();
  const { idSet } = useBookmarkIds();
  const { toggle, isPending } = useToggleBookmark();

  if (isAuthDisabled()) return null;

  const numericId = Number(paperId);
  const isBookmarked = !!user && idSet.has(numericId);

  const handleClick = () => {
    if (!Number.isFinite(numericId)) return;
    toggle(numericId, isBookmarked);
  };

  const label = !user ? "Save" : isBookmarked ? "Saved" : "Save";
  const ariaLabel = !user
    ? "Sign in with Hugging Face to save this paper"
    : isBookmarked
      ? "Remove from saved papers"
      : "Save this paper";

  return (
    <button
      type="button"
      className={`action-btn${isBookmarked ? " is-saved" : ""}`}
      onClick={handleClick}
      disabled={isPending}
      aria-pressed={isBookmarked}
      aria-label={ariaLabel}
      title={ariaLabel}
    >
      <Icon name="bookmark" size={12} />
      {label}
    </button>
  );
};

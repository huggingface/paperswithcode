import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { AuthorAvatar } from "@/components/AuthorAvatar";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { papersApi } from "@/lib/api/papers";

const isCoarsePointer = (): boolean =>
  typeof window.matchMedia === "function" &&
  window.matchMedia("(hover: none), (pointer: coarse)").matches;

/** One of the paper's authors with a Papers with Code author page. */
export interface PdfPaperAuthor {
  id: string;
  name: string;
  avatarUrl?: string | null;
}

export interface PdfAuthorLinkTarget extends PdfPaperAuthor {
  /** Page 0–1000 grid: x0, y0, x1, y1. */
  box: number[];
}

// An author's name on the first page, positioned over the name's text. Its
// card shows the author's profile; the name and the card open the author page.
export function PdfAuthorLink({ id, name, avatarUrl, box: [x0, y0, x1, y1] }: PdfAuthorLinkTarget) {
  const [open, setOpen] = useState(false);
  const href = `/authors/${encodeURIComponent(id)}`;
  const author = useQuery({
    queryKey: ["author", id],
    queryFn: () => papersApi.getAuthor(id),
    enabled: open,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  const paperCount = author.data?.paper_count;
  const handle = author.data?.hf_username;
  return <div
    className="pdf-author-link"
    style={{ left: `${x0 / 10}%`, top: `${y0 / 10}%`, width: `${(x1 - x0) / 10}%`, height: `${(y1 - y0) / 10}%` }}
  >
    <HoverCard
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen || !isCoarsePointer()) setOpen(nextOpen);
      }}
      openDelay={150}
      closeDelay={100}
    >
      <HoverCardTrigger asChild>
        <Link
          to={href}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Author ${name}`}
          onClick={() => setOpen(false)}
        />
      </HoverCardTrigger>
      <HoverCardContent className="paper-preview-pop" side="bottom" align="start" collisionPadding={12}>
        <Link className="pdf-author-card" to={href} target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)}>
          <AuthorAvatar url={author.data?.hf_avatar_url ?? avatarUrl} className="pdf-author-card-avatar" />
          <div className="pdf-author-card-meta">
            <div className="paper-preview-title">{author.data?.full_name ?? name}</div>
            <div className="paper-preview-auth">
              {paperCount != null && `${paperCount.toLocaleString()} ${paperCount === 1 ? "paper" : "papers"}`}
              {paperCount != null && handle && " · "}
              {handle && `@${handle}`}
            </div>
          </div>
        </Link>
        <div className="pdf-paper-preview-actions">
          <Link to={href} target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)}>Open author page ↗</Link>
        </div>
      </HoverCardContent>
    </HoverCard>
  </div>;
}

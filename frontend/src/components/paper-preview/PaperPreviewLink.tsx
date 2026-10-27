import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import {
  PaperPreviewCard,
} from "@/components/paper-preview/PaperPreviewCard";
import { paperPreviewQueryKey } from "@/components/paper-preview/paperPreviewCache";
import { ARXIV_ROUTE_ID, PaperIndexRequest } from "@/components/paper-preview/PaperIndexRequest";
import {
  paperToPreviewData,
  type PaperPreviewData,
} from "@/components/paper-preview/paperPreviewData";
import { papersApi } from "@/lib/api/papers";
import { ApiError } from "@/lib/apiTransport";
import { normalizePaperRouteId } from "@/lib/utils";

interface PaperPreviewLinkProps {
  routeId: string;
  to?: string;
  initialData?: PaperPreviewData;
  className?: string;
  children: React.ReactNode;
  target?: React.HTMLAttributeAnchorTarget;
  title?: string;
  ariaLabel?: string;
  onClick?: React.MouseEventHandler<HTMLAnchorElement>;
  previewFooter?: (data: PaperPreviewData) => React.ReactNode;
  /** Makes the loaded card itself a link that opens the paper in a new tab. */
  cardOpensPaper?: boolean;
}

const isCoarsePointer = (): boolean =>
  typeof window.matchMedia === "function" &&
  window.matchMedia("(hover: none), (pointer: coarse)").matches;

export const PaperPreviewLink: React.FC<PaperPreviewLinkProps> = ({
  routeId,
  to,
  initialData,
  className,
  children,
  target,
  title,
  ariaLabel,
  onClick,
  previewFooter,
  cardOpensPaper = false,
}) => {
  const normalizedRouteId = normalizePaperRouteId(routeId);
  const [open, setOpen] = React.useState(false);
  const hasInitialData = Boolean(initialData?.title.trim());
  const query = useQuery({
    queryKey: paperPreviewQueryKey(normalizedRouteId),
    queryFn: () => papersApi.get(normalizedRouteId, false),
    enabled: open && !hasInitialData,
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    retry: false,
  });
  const data =
    initialData ??
    (query.data
      ? paperToPreviewData(query.data, normalizedRouteId)
      : undefined);
  const notIndexed =
    query.error instanceof ApiError &&
    query.error.status === 404 &&
    ARXIV_ROUTE_ID.test(normalizedRouteId);

  const link = (
    <Link
      className={className}
      to={to ?? `/paper/${normalizedRouteId}`}
      target={target}
      title={title}
      aria-label={ariaLabel}
      onClick={(event) => { setOpen(false); onClick?.(event); }}
      rel={target === "_blank" ? "noopener noreferrer" : undefined}
    >
      {children}
    </Link>
  );

  return (
    <HoverCard
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen || !isCoarsePointer()) setOpen(nextOpen);
      }}
      openDelay={150}
      closeDelay={100}
    >
      <HoverCardTrigger asChild>{link}</HoverCardTrigger>
      <HoverCardContent
        className="paper-preview-pop"
        side="bottom"
        align="start"
        collisionPadding={12}
      >
        {data ? (
          <>
            {cardOpensPaper ? (
              <Link
                className="paper-preview-card-link"
                to={`/paper/${encodeURIComponent(normalizedRouteId)}`}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => setOpen(false)}
              >
                <PaperPreviewCard data={data} />
              </Link>
            ) : (
              <PaperPreviewCard data={data} />
            )}
            {previewFooter?.(data)}
          </>
        ) : notIndexed ? (
          <PaperIndexRequest arxivId={normalizedRouteId} />
        ) : query.isError ? (
          <div className="paper-preview-status">Preview unavailable</div>
        ) : (
          <div className="paper-preview-status" aria-live="polite">
            Loading preview…
          </div>
        )}
      </HoverCardContent>
    </HoverCard>
  );
};

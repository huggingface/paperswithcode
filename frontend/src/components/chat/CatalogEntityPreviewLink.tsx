/**
 * Hover-preview links for catalog citations in chat answers:
 * `[label](task:<slug>)`, `[label](method:<slug>)`, and
 * `[label](benchmark:<slug>)`. The card is fetched lazily on first hover
 * from the same public endpoints the task, method, and benchmark pages use.
 */

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { catalogApi } from "@/lib/api/catalog";
import { assetUrl } from "@/lib/apiUrl";

export type CatalogEntityKind = "task" | "method" | "benchmark";

export interface CatalogEntityRef {
  kind: CatalogEntityKind;
  slug: string;
}

const KIND_PREFIX = /^(task|method|benchmark):([A-Za-z0-9][A-Za-z0-9._-]{0,199})$/;

export function parseCatalogEntityHref(href: string): CatalogEntityRef | null {
  const match = KIND_PREFIX.exec(href);
  return match ? { kind: match[1] as CatalogEntityKind, slug: match[2] } : null;
}

export const isCatalogEntityHref = (href: string): boolean =>
  /^(task|method|benchmark):/.test(href);

const ENTITY_PATH: Record<CatalogEntityKind, string> = {
  task: "/tasks/",
  method: "/methods/",
  benchmark: "/benchmark/",
};

const KIND_LABEL: Record<CatalogEntityKind, string> = {
  task: "Task",
  method: "Method",
  benchmark: "Benchmark",
};

interface CatalogEntityPreview {
  name: string;
  description: string | null;
  imageUrl: string | null;
  paperCount: number | null;
  detail: string | null;
}

async function fetchPreview({ kind, slug }: CatalogEntityRef): Promise<CatalogEntityPreview> {
  if (kind === "task") {
    const task = await catalogApi.getTask(slug);
    return {
      name: task.name,
      description: task.description ?? null,
      imageUrl: task.image_url ?? null,
      paperCount: task.paper_count ?? null,
      detail: null,
    };
  }
  if (kind === "method") {
    const method = await catalogApi.getMethod(slug);
    return {
      name: method.full_name || method.name,
      description: method.description ?? null,
      imageUrl: method.image_url ?? null,
      paperCount: method.paper_count ?? null,
      detail: method.introduced_year ? `Introduced ${method.introduced_year}` : null,
    };
  }
  const dataset = await catalogApi.getDatasetBySlug(slug);
  return {
    name: dataset.full_name || dataset.name,
    description: dataset.description ?? null,
    imageUrl: null,
    paperCount: dataset.paper_count ?? null,
    detail: dataset.introduced_year ? `Introduced ${dataset.introduced_year}` : null,
  };
}

/** Flatten catalog Markdown descriptions into a short plain-text excerpt. */
function plainExcerpt(markdown: string): string {
  return markdown
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[*_`#>]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

const isCoarsePointer = (): boolean =>
  typeof window.matchMedia === "function" &&
  window.matchMedia("(hover: none), (pointer: coarse)").matches;

const CatalogEntityCard: React.FC<{
  kind: CatalogEntityKind;
  preview: CatalogEntityPreview;
}> = ({ kind, preview }) => {
  const [imageFailed, setImageFailed] = React.useState(false);
  const imageUrl = assetUrl(preview.imageUrl);
  const stats = [
    preview.paperCount != null
      ? `${preview.paperCount.toLocaleString()} ${preview.paperCount === 1 ? "paper" : "papers"}`
      : null,
    preview.detail,
  ].filter(Boolean);

  return (
    <div className="catalog-preview-card">
      {imageUrl && !imageFailed && (
        <img
          className="catalog-preview-image"
          data-testid="catalog-preview-image"
          src={imageUrl}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setImageFailed(true)}
        />
      )}
      <div className="catalog-preview-meta">
        <span className="catalog-preview-kind">{KIND_LABEL[kind]}</span>
        <strong>{preview.name}</strong>
        {preview.description && <p>{plainExcerpt(preview.description)}</p>}
        {stats.length > 0 && (
          <span className="catalog-preview-stats">{stats.join(" · ")}</span>
        )}
      </div>
    </div>
  );
};

export const CatalogEntityPreviewLink: React.FC<{
  entity: CatalogEntityRef;
  children: React.ReactNode;
}> = ({ entity, children }) => {
  const [open, setOpen] = React.useState(false);
  const query = useQuery({
    queryKey: ["chat-catalog-preview", entity.kind, entity.slug],
    queryFn: () => fetchPreview(entity),
    enabled: open,
    staleTime: 10 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    retry: false,
  });

  return (
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
          className="chat-paper-link"
          to={`${ENTITY_PATH[entity.kind]}${encodeURIComponent(entity.slug)}`}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => setOpen(false)}
        >
          {children}
        </Link>
      </HoverCardTrigger>
      <HoverCardContent
        className="catalog-preview-pop"
        side="bottom"
        align="start"
        collisionPadding={12}
      >
        {query.data ? (
          <CatalogEntityCard kind={entity.kind} preview={query.data} />
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

import { CatalogEntityPreviewLink } from "@/components/chat/CatalogEntityPreviewLink";
import { LatexText } from "@/components/LatexTitle";
import type { AbstractMention } from "@/lib/api/papers.types";

/**
 * A paper abstract with its linked catalog names: each mention becomes a hover
 * link to the method, benchmark, or framework page, and the rest renders
 * through LatexText.
 */
export function AbstractText({
  abstract,
  mentions,
}: {
  abstract: string;
  mentions: AbstractMention[];
}) {
  const parts: React.ReactNode[] = [];
  let at = 0;
  for (const mention of [...mentions].sort((a, b) => a.start - b.start)) {
    if (mention.start < at || mention.end > abstract.length) continue;
    if (abstract.slice(mention.start, mention.end) !== mention.surface) continue;
    parts.push(<LatexText key={`t${at}`} text={abstract.slice(at, mention.start)} />);
    parts.push(
      <CatalogEntityPreviewLink
        key={`m${mention.start}`}
        entity={{ kind: mention.entity_type, slug: mention.slug }}
        className="abstract-entity-link"
        newTab={false}
        initialPreview={
          mention.preview
            ? {
                name: mention.preview.name,
                description: mention.preview.description ?? null,
                imageUrl: mention.preview.image_url ?? null,
                count: mention.preview.count ?? null,
                detail: mention.preview.detail ?? null,
              }
            : undefined
        }
      >
        {mention.surface}
      </CatalogEntityPreviewLink>,
    );
    at = mention.end;
  }
  parts.push(<LatexText key={`t${at}`} text={abstract.slice(at)} />);
  return <>{parts}</>;
}

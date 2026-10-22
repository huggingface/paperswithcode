import { CatalogEntityPreviewLink } from "@/components/chat/CatalogEntityPreviewLink";
import { LatexText } from "@/components/LatexTitle";
import type { AbstractMention } from "@/lib/api/papers.types";

/**
 * A paper abstract with its linked catalog names: each mention becomes a hover
 * link to the method, benchmark, or framework page, and the rest renders
 * through LatexText. `visibleLength` cuts the collapsed preview; a mention that
 * crosses the cut stays plain text until the abstract is expanded.
 */
export function AbstractText({
  abstract,
  mentions,
  visibleLength,
}: {
  abstract: string;
  mentions: AbstractMention[];
  visibleLength: number | null;
}) {
  const limit = visibleLength ?? abstract.length;
  const parts: React.ReactNode[] = [];
  let at = 0;
  for (const mention of [...mentions].sort((a, b) => a.start - b.start)) {
    if (mention.start < at || mention.end > limit) continue;
    if (abstract.slice(mention.start, mention.end) !== mention.surface) continue;
    parts.push(<LatexText key={`t${at}`} text={abstract.slice(at, mention.start)} />);
    parts.push(
      <CatalogEntityPreviewLink
        key={`m${mention.start}`}
        entity={{ kind: mention.entity_type, slug: mention.slug }}
        className="abstract-entity-link"
        newTab={false}
      >
        {mention.surface}
      </CatalogEntityPreviewLink>,
    );
    at = mention.end;
  }
  parts.push(<LatexText key={`t${at}`} text={abstract.slice(at, limit)} />);
  return (
    <>
      {parts}
      {visibleLength !== null && "…"}
    </>
  );
}

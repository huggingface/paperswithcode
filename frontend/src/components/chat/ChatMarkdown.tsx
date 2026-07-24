/**
 * Streaming-safe renderer for the assistant's Markdown answer text, including
 * inline paper citations of the form `[label](paper:<arxiv_id>)`.
 *
 * Citations render as links to the paper page with a hover-preview card fed
 * by the metadata collected from earlier `search_papers` tool results. While
 * the text is still streaming, a half-typed citation at the tail is withheld
 * so raw markdown never flashes on screen.
 */

import React from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import { Link } from "react-router-dom";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import type { ChatPaperHit } from "@/lib/chat";
import { authorsLine, venueLine } from "@/components/chat/paperDisplay";
import { assetUrl } from "@/lib/apiUrl";

/** Faux first-page thumbnail so hover cards need no remote assets. */
export const FauxPaperThumb: React.FC<{ seed?: number }> = ({ seed = 0 }) => (
  <div className="chat-thumb" aria-hidden="true">
    <div className="chat-thumb-title">
      <span />
      <span />
    </div>
    <div className="chat-thumb-auth" />
    <div className="chat-thumb-cols">
      <div className="chat-thumb-col" />
      <div className="chat-thumb-col" />
    </div>
    <div className="chat-thumb-fig" style={{ top: 62 + (seed % 3) * 8 }} />
  </div>
);

const PaperThumb: React.FC<{ paper: ChatPaperHit; seed: number }> = ({ paper, seed }) => {
  const [errored, setErrored] = React.useState(false);
  const thumbnailUrl = assetUrl(paper.metadata.thumbnail_url);

  React.useEffect(() => setErrored(false), [thumbnailUrl]);

  if (!thumbnailUrl || errored) return <FauxPaperThumb seed={seed} />;
  return (
    <div className="chat-thumb chat-thumb-real">
      <img
        src={thumbnailUrl}
        alt=""
        loading="lazy"
        decoding="async"
        onError={() => setErrored(true)}
      />
    </div>
  );
};

export const PaperCitation: React.FC<{
  routeId: string;
  paper?: ChatPaperHit;
  className?: string;
  children: React.ReactNode;
}> = ({ routeId, paper, className = "chat-paper-link", children }) => {
  const link = (
    <Link
      className={className}
      to={`/paper/${routeId}`}
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
    </Link>
  );
  if (!paper) return link;

  const m = paper.metadata;
  const seed = routeId.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  return (
    <HoverCard openDelay={150} closeDelay={100}>
      <HoverCardTrigger asChild>{link}</HoverCardTrigger>
      <HoverCardContent className="chat-paper-pop" side="bottom" align="start">
        <div className="chat-paper-pop-inner">
          <PaperThumb paper={paper} seed={seed} />
          <div className="chat-paper-pop-meta">
            <div className="chat-paper-pop-title">{paper.title}</div>
            {authorsLine(m) && <div className="chat-paper-pop-auth">{authorsLine(m)}</div>}
            <div className="chat-paper-pop-venue">
              {venueLine(m)}
              {m.arxiv_id && <> · arXiv:{m.arxiv_id}</>}
              {m.citation_count != null && <> · ↑ {m.citation_count.toLocaleString()}</>}
            </div>
            {m.tasks.length > 0 && (
              <div className="chat-paper-pop-tags">
                {m.tasks.map((t) => (
                  <span key={t.slug} className="chat-pp-tag">
                    {t.name}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
};

/**
 * Drop an incomplete trailing citation (e.g. `[YOLOv12](paper:25`) so it
 * doesn't flash as raw markdown mid-stream. Complete text passes through.
 */
function withholdPartialCitation(text: string): string {
  const open = text.lastIndexOf("[");
  if (open === -1) return text;
  const tail = text.slice(open);
  if (/^\[[^\]]*(\]\(?[^)\s]*)?$/.test(tail)) return text.slice(0, open);
  return text;
}

const chatUrlTransform = (url: string): string =>
  url.startsWith("paper:") ? url : defaultUrlTransform(url);

export const ChatMarkdown: React.FC<{
  text: string;
  streaming?: boolean;
  papers: Record<string, ChatPaperHit>;
  validCitationIds?: Set<string>;
}> = ({ text, streaming, papers, validCitationIds }) => {
  const source = streaming ? withholdPartialCitation(text) : text;

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      urlTransform={chatUrlTransform}
      components={{
        a: ({ href, children }) => {
          if (href?.startsWith("paper:")) {
            const routeId = href.slice("paper:".length);
            if (!papers[routeId] && !validCitationIds?.has(routeId)) {
              return <span className="chat-invalid-citation">{children}</span>;
            }
            return (
              <PaperCitation routeId={routeId} paper={papers[routeId]}>
                {children}
              </PaperCitation>
            );
          }
          return <span>{children}</span>;
        },
      }}
    >
      {source}
    </ReactMarkdown>
  );
};

/**
 * Streaming-safe renderer for the assistant's Markdown answer text, including
 * inline paper citations of the form `[label](paper:<arxiv_id>)` and catalog
 * citations of the form `[label](task|method|benchmark:<slug>)`.
 *
 * Citations render as links to the paper page with a hover-preview card fed
 * by the metadata collected from earlier `search_papers` tool results. While
 * the text is still streaming, a half-typed citation at the tail is withheld
 * so raw markdown never flashes on screen.
 */

import React from "react";
import { Github } from "lucide-react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

import type {
  ChatCitation,
  ChatPaperHit,
} from "@/lib/chat";
import {
  HuggingFacePreviewLink,
  parseHuggingFaceRepoUrl,
} from "@/components/chat/HuggingFacePreviewLink";
import { GitHubPreviewLink } from "@/components/chat/GitHubPreviewLink";
import { PdfCitationChip, PdfCitationSources } from "@/components/chat/PdfCitation";
import { PDF_CITATION_ANCHOR } from "@/components/pdf/pdfCitations";
import { WebPreviewLink } from "@/components/chat/WebPreviewLink";
import { ExternalPaperPreviewLink } from "@/components/chat/ExternalPaperPreviewLink";
import {
  CatalogEntityPreviewLink,
  isCatalogEntityHref,
  parseCatalogEntityHref,
} from "@/components/chat/CatalogEntityPreviewLink";
import { PaperPreviewLink } from "@/components/paper-preview/PaperPreviewLink";
import type { PaperPreviewData } from "@/components/paper-preview/paperPreviewData";
import { parseGitHubRepoUrl } from "@/lib/github";
import { normalizeChatMath } from "@/components/chat/chatMarkdownMath";

function citationPreviewData(
  routeId: string,
  paper?: ChatPaperHit,
  citation?: ChatCitation,
): PaperPreviewData | undefined {
  if (paper) {
    return {
      routeId,
      title: paper.title,
      arxivId: paper.metadata.arxiv_id,
      source: paper.metadata.source,
      sourceUrl: paper.metadata.source_url,
      thumbnailUrl: paper.metadata.thumbnail_url,
      authors: paper.metadata.authors.map((author) => author.name),
      published: paper.metadata.published,
      conference: paper.metadata.conference,
      citationCount: paper.metadata.citation_count,
      tasks: paper.metadata.tasks,
    };
  }
  if (!citation) return undefined;
  return {
    routeId,
    title: citation.title,
    arxivId: citation.arxiv_id ?? null,
    source: citation.arxiv_id ? "arxiv" : "external",
    sourceUrl: citation.source_url,
    thumbnailUrl: citation.thumbnail_url ?? null,
    authors: citation.authors ?? [],
    published: citation.published ?? null,
    conference: citation.conference ?? null,
    citationCount: citation.citation_count ?? null,
    tasks: [],
  };
}

export const PaperCitation: React.FC<{
  routeId: string;
  paper?: ChatPaperHit;
  citation?: ChatCitation;
  className?: string;
  children: React.ReactNode;
}> = ({ routeId, paper, citation, className = "chat-paper-link", children }) => {
  return (
    <PaperPreviewLink
      routeId={routeId}
      initialData={citationPreviewData(routeId, paper, citation)}
      className={className}
      target="_blank"
    >
      {children}
    </PaperPreviewLink>
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
  url.startsWith("paper:") || url.startsWith("pdf:") || isCatalogEntityHref(url)
    ? url
    : defaultUrlTransform(url);

function isGitHubUrl(href: string): boolean {
  try {
    const url = new URL(href);
    return (
      url.protocol === "https:" &&
      (url.hostname === "github.com" || url.hostname === "www.github.com")
    );
  } catch {
    return false;
  }
}

export const ChatMarkdown: React.FC<{
  text: string;
  streaming?: boolean;
  papers: Record<string, ChatPaperHit>;
  citations?: Record<string, ChatCitation>;
  webCitations?: Record<string, ChatCitation>;
}> = ({ text, streaming, papers, citations, webCitations }) => {
  const source = normalizeChatMath(
    streaming ? withholdPartialCitation(text) : text,
  );

  return (
    <>
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      urlTransform={chatUrlTransform}
      components={{
        a: ({ href, children }) => {
          if (href?.startsWith("paper:")) {
            const routeId = href.slice("paper:".length);
            if (!papers[routeId] && !citations?.[routeId]) {
              return <span className="chat-invalid-citation">{children}</span>;
            }
            return (
              <PaperCitation
                routeId={routeId}
                paper={papers[routeId]}
                citation={citations?.[routeId]}
              >
                {children}
              </PaperCitation>
            );
          }
          if (href?.startsWith("pdf:")) {
            const anchor = href.slice("pdf:".length);
            return PDF_CITATION_ANCHOR.test(anchor)
              ? <PdfCitationChip anchor={anchor}>{children}</PdfCitationChip>
              : <span className="chat-invalid-citation">{children}</span>;
          }
          if (href && isCatalogEntityHref(href)) {
            const entity = parseCatalogEntityHref(href);
            if (!entity) {
              return <span className="chat-invalid-citation">{children}</span>;
            }
            return (
              <CatalogEntityPreviewLink entity={entity}>
                {children}
              </CatalogEntityPreviewLink>
            );
          }
          const huggingFaceRepo = href
            ? parseHuggingFaceRepoUrl(href)
            : null;
          if (huggingFaceRepo) {
            return (
              <HuggingFacePreviewLink repo={huggingFaceRepo}>
                {children}
              </HuggingFacePreviewLink>
            );
          }
          const gitHubRepo = href ? parseGitHubRepoUrl(href) : null;
          if (gitHubRepo) {
            return (
              <GitHubPreviewLink repo={gitHubRepo}>
                {children}
              </GitHubPreviewLink>
            );
          }
          if (href && isGitHubUrl(href)) {
            return (
              <a
                href={href}
                className="chat-github-link"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Github aria-hidden="true" />
                {children}
              </a>
            );
          }
          if (href?.startsWith("https://") && webCitations?.[href]) {
            if (webCitations[href].source_type === "paper") {
              return (
                <ExternalPaperPreviewLink citation={webCitations[href]}>
                  {children}
                </ExternalPaperPreviewLink>
              );
            }
            return (
              <WebPreviewLink citation={webCitations[href]}>
                {children}
              </WebPreviewLink>
            );
          }
          if (href?.startsWith("https://")) {
            return (
              <a
                href={href}
                className="chat-external-link"
                target="_blank"
                rel="noopener noreferrer"
              >
                {children}
              </a>
            );
          }
          return <span>{children}</span>;
        },
      }}
    >
      {source}
    </ReactMarkdown>
    {!streaming && <PdfCitationSources text={source} />}
    </>
  );
};

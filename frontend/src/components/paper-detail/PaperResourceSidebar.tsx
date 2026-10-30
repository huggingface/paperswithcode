import { useState } from "react";

import { Icon } from "@/components/Icon";
import { Skeleton } from "@/components/ui/skeleton";
import type { Paper, RelatedPaperRecommendation } from "@/lib/api/papers.types";
import type { AuthUser } from "@/lib/authContext";
import type { HuggingFaceArtifactsViewer } from "@/lib/paperDetailPresentation";
import { safeExternalHref } from "@/lib/safeExternalHref";

import { CopyToBucketCard, paperArtifactBucketName } from "./CopyToBucketCard";
import { RelatedPapersCard } from "./RelatedPapersCard";
import { XThreadsCard } from "./XThreadsCard";

const REPO_PREVIEW_LIMIT = 3;
const HF_LINK_PREVIEW_LIMIT = 3;

interface HfRowProps {
  label: string;
  href: string;
  count: number | undefined;
  isLimited?: boolean;
  links?: Array<{ label: string; href: string }>;
}

function formatStars(count: number): string {
  return count >= 1000 ? `${(count / 1000).toFixed(1)}k` : String(count);
}

export function PaperResourceSidebar({
  allHfArtifactUrls,
  citationCopied,
  citationDisplay,
  hfArtifactViewer,
  onCopyCitation,
  onEditHfArtifacts,
  onEditRepositories,
  onEditXThreads,
  paper,
  relatedIsLoading,
  relatedPapers,
  user,
}: {
  allHfArtifactUrls: { models: string[]; datasets: string[]; spaces: string[] };
  citationCopied: boolean;
  citationDisplay: string;
  hfArtifactViewer: HuggingFaceArtifactsViewer;
  onCopyCitation: () => void;
  onEditHfArtifacts: () => void;
  onEditRepositories: () => void;
  onEditXThreads: () => void;
  paper: Paper;
  relatedIsLoading: boolean;
  relatedPapers?: RelatedPaperRecommendation[];
  user: AuthUser | null;
}) {
  const [reposExpanded, setReposExpanded] = useState(false);
  const sortedRepos = [...(paper.repositories ?? [])].sort((a, b) => {
    const officialDifference = Number(b.is_official) - Number(a.is_official);
    return officialDifference || (b.num_stars || 0) - (a.num_stars || 0);
  });
  const visibleRepos = (reposExpanded
    ? sortedRepos
    : sortedRepos.slice(0, REPO_PREVIEW_LIMIT)
  ).map((repository) => ({
    ...repository,
    safeHref: safeExternalHref(repository.url),
  }));

  return (
    <aside className="detail-sidebar">
      <div className="sidebar-card">
        <div className="sidebar-card-title">
          <span>GitHub</span>
          <span className="badge">
            {sortedRepos.length} repo{sortedRepos.length === 1 ? "" : "s"}
            <button type="button" onClick={onEditRepositories} className="edit-link">
              edit
            </button>
          </span>
        </div>
        {visibleRepos.filter(({ safeHref }) => safeHref).map((repository) => (
          <a
            key={repository.id}
            href={repository.safeHref ?? undefined}
            target="_blank"
            rel="noopener noreferrer"
            className="code-line"
            style={{ textDecoration: "none" }}
          >
            <span className="code-line-repo">
              <Icon name="github" size={12} />
              <span className="code-line-repo-name">
                {repository.owner}/{repository.name}
              </span>
              {repository.is_official && <span className="code-line-official">· Official</span>}
            </span>
            <span className="code-line-stars">★ {formatStars(repository.num_stars)}</span>
          </a>
        ))}
        {sortedRepos.length === 0 && (
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)", padding: "6px 0" }}>
            No GitHub repositories linked yet.
          </div>
        )}
        {sortedRepos.length > REPO_PREVIEW_LIMIT && (
          <button
            type="button"
            className="bench-show-more"
            onClick={() => setReposExpanded((expanded) => !expanded)}
          >
            {reposExpanded
              ? "− show top 3"
              : `+ show ${sortedRepos.length - REPO_PREVIEW_LIMIT} more repos`}
          </button>
        )}
      </div>

      <HuggingFaceArtifactsCard viewer={hfArtifactViewer} onEdit={onEditHfArtifacts} />
      <XThreadsCard threads={paper.x_threads ?? []} onEdit={onEditXThreads} />
      <CopyToBucketCard
        githubUrls={sortedRepos.map(({ url }) => url)}
        hfModelUrls={allHfArtifactUrls.models}
        hfDatasetUrls={allHfArtifactUrls.datasets}
        hfSpaceUrls={allHfArtifactUrls.spaces}
        paperId={paper.id}
        pdfName={paper.arxiv_id?.replace("/", "-") || paper.id}
        pdfUrl={paper.url_pdf}
        isSignedIn={Boolean(user)}
        suggestedBucketId={user ? `${user.username}/${paperArtifactBucketName(paper.title)}` : undefined}
      />
      <RelatedPapersCard isLoading={relatedIsLoading} papers={relatedPapers} />

      <div className="sidebar-card">
        <div className="sidebar-card-title">
          <span>Citation</span>
          <button
            type="button"
            className="citation-copy-btn"
            onClick={onCopyCitation}
            aria-label="Copy citation to clipboard"
            title="Copy citation to clipboard"
          >
            <Icon name="copy" size={11} />
            {citationCopied ? "Copied" : "Copy"}
          </button>
        </div>
        <pre style={{ fontFamily: "var(--mono)", fontSize: 10.5, lineHeight: 1.5, color: "var(--ink-soft)", whiteSpace: "pre-wrap", wordBreak: "break-word", margin: 0 }}>
          {citationDisplay}
        </pre>
      </div>
    </aside>
  );
}

function HuggingFaceArtifactsCard({
  onEdit,
  viewer,
}: {
  onEdit: () => void;
  viewer: HuggingFaceArtifactsViewer;
}) {
  return (
    <div className="sidebar-card">
      <div className="sidebar-card-title">
        {viewer.paperHref ? (
          <a href={viewer.paperHref} target="_blank" rel="noopener noreferrer" style={{ color: "inherit", textDecoration: "none" }}>
            🤗 Hugging Face
          </a>
        ) : <span>🤗 Hugging Face</span>}
        <button type="button" onClick={onEdit} className="edit-link">edit</button>
      </div>
      {viewer.isLoading ? (
        <Skeleton className="h-16 w-full" />
      ) : (
        <>
          {viewer.rows.map((row) => <HfRow key={row.label} {...row} />)}
          {viewer.footer && (
            <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-faint)", marginTop: 12 }}>
              {viewer.footer}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function HfRow({ count, href, isLimited, label, links }: HfRowProps) {
  const [expanded, setExpanded] = useState(false);
  const canExpand = (links?.length ?? 0) > HF_LINK_PREVIEW_LIMIT;
  const visibleLinks = expanded ? links : links?.slice(0, HF_LINK_PREVIEW_LIMIT);
  const countLabel = count != null ? `${count}${isLimited ? "+" : ""}` : "—";

  return (
    <div className="hf-artifact-row">
      <div className="hf-artifact-row-header">
        <span>{label}</span>
        {count ? (
          <a href={href} target="_blank" rel="noopener noreferrer" className="hf-artifact-count">
            {countLabel}
          </a>
        ) : <span className="hf-artifact-count hf-artifact-count--empty">{countLabel}</span>}
      </div>
      {visibleLinks?.length ? (
        <div className="hf-artifact-links">
          {visibleLinks.map((link) => (
            <a key={link.href} href={link.href} target="_blank" rel="noopener noreferrer">{link.label}</a>
          ))}
          {canExpand && (
            <button type="button" className="hf-artifact-toggle" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
              {expanded ? "Show fewer" : `View all ${links!.length}`}
            </button>
          )}
        </div>
      ) : null}
    </div>
  );
}

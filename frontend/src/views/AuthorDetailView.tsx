import React, { useMemo } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { AuthorAvatar } from "@/components/AuthorAvatar";
import { PaperFeedList, PaperFeedToolbar } from "@/components/PaperFeed";
import ResearchFollowButton from "@/components/ResearchFollowButton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { usePaperFeedParams } from "@/hooks/usePaperFeedParams";
import { usePaperFeedQuery } from "@/hooks/usePapers";
import { papersApi } from "@/lib/api/papers";
import { isNotFound } from "@/lib/apiErrors";
import { paperQueryKeys } from "@/lib/paperQueryKeys";
import { transformPaperForCard } from "@/lib/transform";
import NotFound from "@/pages/NotFound";

const AuthorFeed: React.FC<{ authorId: string }> = ({ authorId }) => {
  const feed = usePaperFeedParams();
  const { searchParams } = feed;
  const author = useQuery({
    queryKey: ["author", authorId],
    queryFn: () => papersApi.getAuthor(authorId),
  });
  const papers = usePaperFeedQuery(
    [...paperQueryKeys.feeds.infinite, { author: authorId, ...feed.filters }],
    (page) => papersApi.list({ ...feed.filters, author: authorId, page, page_size: 12 }),
  );

  const cards = useMemo(
    () => (papers.data?.pages ?? []).flatMap((page) => page.results.map(transformPaperForCard)),
    [papers.data],
  );

  const totalCount = papers.data?.pages[0]?.count ?? 0;

  if (isNotFound(author.error)) {
    return <NotFound />;
  }
  // arXiv group authors such as "NVIDIA" are organizations, not people.
  if (author.data?.organization_slug) {
    const search = searchParams.toString();
    return <Navigate to={`/orgs/${author.data.organization_slug}${search ? `?${search}` : ""}`} replace />;
  }

  return (
    <div className="page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <span> / </span>
        <span>Authors</span>
        <span> / </span>
        <span>{author.data?.full_name ?? authorId}</span>
      </nav>

      <header className="author-hero">
        <div className="organizations-eyebrow">AUTHOR</div>
        <div className="author-hero-title">
          {author.data?.photo ? (
            <figure className="author-photo">
              <img className="author-avatar-base author-avatar" src={author.data.photo.url} alt="" />
              <figcaption>
                Photo:{" "}
                <a href={author.data.photo.source_url} target="_blank" rel="noopener noreferrer">
                  {author.data.photo.credit}
                </a>
                {", "}
                {author.data.photo.license_url ? (
                  <a href={author.data.photo.license_url} target="_blank" rel="noopener noreferrer">
                    {author.data.photo.license}
                  </a>
                ) : (
                  author.data.photo.license
                )}
              </figcaption>
            </figure>
          ) : author.data?.hf_username && (
            <AuthorAvatar
              className="author-avatar"
              url={author.data.hf_avatar_url}
              href={`https://huggingface.co/${author.data.hf_username}`}
              label={`@${author.data.hf_username} on Hugging Face`}
            />
          )}
          <h1 className="feed-title">
            {author.data?.full_name ?? <Skeleton className="h-12 w-64 inline-block" />}
          </h1>
        </div>
        {author.data && (
          <div className="feed-subtitle">
            {author.data.paper_count.toLocaleString()}{" "}
            {author.data.paper_count === 1 ? "paper" : "papers"}
            {author.data.hf_username && (
              <>
                {" · "}
                <a
                  href={`https://huggingface.co/${author.data.hf_username}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  @{author.data.hf_username} on Hugging Face ↗
                </a>
              </>
            )}
            {author.data.google_scholar_id && (
              <>
                {" · "}
                <a
                  href={`https://scholar.google.com/citations?user=${encodeURIComponent(author.data.google_scholar_id)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Google Scholar ↗
                </a>
              </>
            )}
          </div>
        )}
        {author.data && <ResearchFollowButton kind="author" entityId={author.data.id} />}
      </header>

      <PaperFeedToolbar feed={feed} style={{ alignItems: "center", gap: 16 }}>
        <div className="results-count">{totalCount.toLocaleString()} papers</div>
      </PaperFeedToolbar>

      {papers.error ? (
        <Alert variant="destructive">
          <AlertDescription>
            Failed to load papers.{" "}
            <button type="button" onClick={() => void papers.refetch()}>Try again</button>
          </AlertDescription>
        </Alert>
      ) : (
        <PaperFeedList
          query={papers}
          cards={cards}
          empty={
            author.data?.paper_count === 0
              ? "No public papers are available."
              : "No papers found for this selection."
          }
        />
      )}
    </div>
  );
};

// Remount per author so the shared feed never shows the previous author's papers.
const AuthorDetailView: React.FC = () => {
  const { authorId } = useParams<{ authorId: string }>();
  return authorId ? <AuthorFeed key={authorId} authorId={authorId} /> : <NotFound />;
};

export default AuthorDetailView;

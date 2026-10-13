import ResearchFollowButton from "@/components/ResearchFollowButton";
import { paperQueryKeys } from "@/lib/paperQueryKeys";
import React from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { papersApi } from "@/lib/api/papers";
import { Skeleton } from "@/components/ui/skeleton";
import NotFound from "@/pages/NotFound";

const AuthorDetailView: React.FC = () => {
  const { authorId } = useParams<{ authorId: string }>();
  const author = useQuery({
    queryKey: ["author", authorId],
    queryFn: () => papersApi.getAuthor(authorId!),
    enabled: !!authorId,
  });
  const papers = useQuery({
    queryKey: [...paperQueryKeys.feeds.author, authorId],
    queryFn: () => papersApi.authorPapers(authorId!, { page: 1, page_size: 20 }),
    enabled: !!authorId,
  });

  if ((author.error as { status?: number } | null)?.status === 404) {
    return <NotFound />;
  }

  return (
    <div className="page">
      <p className="sidebar-label">Author</p>
      <h1 className="feed-title">
        {author.data?.full_name ?? <Skeleton className="h-10 w-64 inline-block" />}
      </h1>
          {author.data && <ResearchFollowButton kind="author" entityId={author.data.id} />}
      {author.data?.hf_username && (
        <a
          href={`https://huggingface.co/${author.data.hf_username}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          @{author.data.hf_username} on Hugging Face
        </a>
      )}
      <section style={{ marginTop: 40 }} aria-labelledby="author-papers-heading">
        <h2 id="author-papers-heading">Research papers</h2>
        {papers.isLoading && <Skeleton className="h-24 w-full mt-4" />}
        {papers.data?.results.length === 0 && <p>No public papers are available.</p>}
        <ol className="paper-list">
          {papers.data?.results.map((paper) => {
            const routeId = paper.source === "external" ? String(paper.id) : paper.arxiv_id;
            return (
              <li key={paper.id}>
                <Link to={`/paper/${routeId}`}>{paper.title}</Link>
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
};

export default AuthorDetailView;

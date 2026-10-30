import { paperQueryKeys } from "@/lib/paperQueryKeys";
/**
 * Saved papers view (`/saved`).
 *
 * Lists the signed-in user's bookmarked papers grouped by Area (top-level
 * research domain) and within each area sub-grouped by the paper's primary
 * Task. The grouping is computed server-side in `GET /api/v1/me/bookmarks`.
 *
 * If the user is not signed in we render a small sign-in panel that round
 * trips through the HF OAuth flow (same pattern as `HfSignInButton`).
 */

import React from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { PaperCard } from "@/components/PaperCard";
import { TagChip } from "@/components/Chips";
import HfSignInButton from "@/components/HfSignInButton";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { accountApi } from "@/lib/api/account";
import type { SavedPapersResponse } from "@/lib/api/account.types";
import { ApiError } from "@/lib/apiTransport";
import { transformPaperForCard } from "@/lib/transform";
import { useAuth } from "@/lib/authContext";
import { savedPapersAuthorizationUrl } from "@/lib/savedPapersAuth";

const SavedPapersView: React.FC = () => {
  const { user, isLoading: isAuthLoading } = useAuth();

  const query = useQuery<SavedPapersResponse, Error>({
    queryKey: [...paperQueryKeys.feeds.saved],
    queryFn: () => accountApi.getBookmarks(),
    enabled: !!user,
    staleTime: 30 * 1000,
  });
  const bucketAuthorizationRequired =
    query.error instanceof ApiError &&
    query.error.code === "saved_papers_bucket_authorization_required";
  const showBucketMigration = !!query.data && !query.data.bucket_connected;

  const authorizeBucket = () => {
    window.location.assign(savedPapersAuthorizationUrl());
  };

  if (isAuthLoading) {
    return (
      <div className="page">
        <Skeleton className="h-10 w-1/3 mb-4" />
        <Skeleton className="h-6 w-1/2 mb-8" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="page">
        <div className="feed-header">
          <div>
            <h1 className="feed-title">
              Saved <em>Papers</em>
            </h1>
            <div className="feed-subtitle">
              Sign in with Hugging Face to save papers and revisit them later.
            </div>
          </div>
        </div>
        <div className="saved-signin-panel">
          <HfSignInButton returnTo="/saved" />
        </div>
      </div>
    );
  }

  // Position across all task groups, so only the first cards on the page load eagerly.
  let cardPosition = 0;

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            Saved <em>Papers</em>
          </h1>
          <div className="feed-subtitle">
            {query.data?.count
              ? `${query.data.count.toLocaleString()} saved · grouped by domain`
              : "Your bookmarked papers, grouped by domain."}
            {query.data?.bucket_connected ? (
              <>
                {" · "}
                <a
                  href={`https://huggingface.co/buckets/${user.username}/pwc-saved-papers`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open your Hugging Face Bucket
                </a>
              </>
            ) : null}
          </div>
        </div>
      </div>

      {bucketAuthorizationRequired ? (
        <div className="saved-bucket-migration">
          <p>
            Your saved papers are still safe in Papers With Code. Approve Bucket
            access to copy them into a private Hugging Face Bucket that belongs to
            you.
          </p>
          <button type="button" className="hf-signin-btn" onClick={authorizeBucket}>
            Approve and migrate saved papers
          </button>
        </div>
      ) : query.error ? (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>Failed to load your saved papers. Please try again.</AlertDescription>
        </Alert>
      ) : null}

      {showBucketMigration && query.data.bucket_migrated ? (
        <div className="saved-bucket-migration">
          <p>
            Your saved papers are already in your private Hugging Face Bucket.
            Reconnect it in this browser to read from it and save new papers
            there.
          </p>
          <button type="button" className="hf-signin-btn" onClick={authorizeBucket}>
            Reconnect Hugging Face Bucket
          </button>
        </div>
      ) : showBucketMigration ? (
        <div className="saved-bucket-migration">
          <p>
            {query.data.count
              ? `Your ${query.data.count.toLocaleString()} saved ${query.data.count === 1 ? "paper is" : "papers are"} still available below. `
              : "When you save your first paper, "}
            Approve Bucket access to copy saved papers into a private Hugging Face
            Bucket that belongs to you. The existing data is kept until the copy is
            verified.
          </p>
          <button type="button" className="hf-signin-btn" onClick={authorizeBucket}>
            {query.data.count
              ? "Approve and migrate saved papers"
              : "Use a Hugging Face Bucket"}
          </button>
        </div>
      ) : null}

      {bucketAuthorizationRequired || query.error ? null : query.isLoading ? (
        <div className="paper-list">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="paper-card">
              <Skeleton className="h-[220px] w-[160px]" />
              <div className="paper-body" style={{ flex: 1, gap: 12 }}>
                <Skeleton className="h-6 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-12 w-full" />
              </div>
            </div>
          ))}
        </div>
      ) : !query.data || query.data.count === 0 ? (
        <div className="no-results">
          No saved papers yet.{" "}
          <Link to="/papers" className="sidebar-link" style={{ display: "inline" }}>
            Browse papers →
          </Link>
        </div>
      ) : (
        query.data.areas.map((area) => (
          <section
            key={`area-${area.id ?? "other"}`}
            className="saved-area-section"
          >
            <h2 className="saved-area-heading">{area.name}</h2>
            {area.tasks.map((task) => {
              const paperCount = task.papers.length;
              return (
                <div
                  key={`task-${area.id ?? "other"}-${task.id ?? "untagged"}`}
                  className="saved-task-block"
                >
                  <div className="saved-task-row">
                    {task.slug ? (
                      <TagChip slug={task.slug} label={task.name} />
                    ) : (
                      <span className="tag-chip" style={{ background: "var(--surface)" }}>
                        {task.name}
                      </span>
                    )}
                    <span className="saved-task-count">
                      {paperCount} {paperCount === 1 ? "paper" : "papers"}
                    </span>
                  </div>
                  <div className="paper-list">
                    {task.papers.map((paper) => (
                      <PaperCard
                        key={paper.id}
                        paper={transformPaperForCard(paper)}
                        priority={cardPosition++ < 3}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </section>
        ))
      )}
    </div>
  );
};

export default SavedPapersView;

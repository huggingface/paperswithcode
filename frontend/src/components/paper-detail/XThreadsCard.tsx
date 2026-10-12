import { Fragment, useState } from "react";

import type { XThread } from "@/lib/api/papers.types";
import { safeExternalHref } from "@/lib/safeExternalHref";

const URL_PATTERN = /(https?:\/\/[^\s]+)/g;

function XLogo({ size = 12 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"
      />
    </svg>
  );
}

function formatCount(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k`;
  return String(count);
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

/** Post text with URLs shown without their scheme. The whole card is a link,
 *  so nested anchors are avoided and URLs stay plain, underlined text. */
function PostText({ text }: { text: string }) {
  return (
    <p className="x-thread-text">
      {text.split(URL_PATTERN).map((part, index) =>
        index % 2 === 1 ? (
          <span key={index} className="x-thread-link">
            {part.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}
          </span>
        ) : (
          <Fragment key={index}>{part}</Fragment>
        ),
      )}
    </p>
  );
}

function Avatar({ thread }: { thread: XThread }) {
  const [failed, setFailed] = useState(false);
  if (!thread.author_avatar_url || failed) {
    return (
      <span className="x-thread-avatar x-thread-avatar--fallback" aria-hidden="true">
        {thread.author_name.charAt(0).toUpperCase()}
      </span>
    );
  }
  return (
    <img
      className="x-thread-avatar"
      src={thread.author_avatar_url}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}

function XThreadPreview({ thread }: { thread: XThread }) {
  const [mediaFailed, setMediaFailed] = useState(false);
  const href = safeExternalHref(thread.url);
  if (!href) return null;

  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="x-thread">
      <div className="x-thread-header">
        <Avatar thread={thread} />
        <span className="x-thread-author">
          <span className="x-thread-name">{thread.author_name}</span>
          <span className="x-thread-handle">@{thread.author_handle}</span>
        </span>
        <span className="x-thread-logo"><XLogo /></span>
      </div>
      <PostText text={thread.text} />
      {thread.media_url && !mediaFailed && (
        <div className="x-thread-media">
          <img
            src={thread.media_url}
            alt=""
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={() => setMediaFailed(true)}
          />
          {thread.media_type === "video" && <span className="x-thread-play" aria-label="Video">▶</span>}
        </div>
      )}
      <div className="x-thread-meta">
        {thread.posted_at && <time dateTime={thread.posted_at}>{formatDate(thread.posted_at)}</time>}
        {thread.like_count != null && <span>♥ {formatCount(thread.like_count)}</span>}
        {thread.reply_count != null && thread.reply_count > 0 && (
          <span>{formatCount(thread.reply_count)} {thread.reply_count === 1 ? "reply" : "replies"}</span>
        )}
        <span className="x-thread-read">Read on X →</span>
      </div>
    </a>
  );
}

export function XThreadsCard({ onEdit, threads }: { onEdit: () => void; threads: XThread[] }) {
  return (
    <div className="sidebar-card">
      <div className="sidebar-card-title">
        <span>X threads</span>
        <span className="badge">
          {threads.length} post{threads.length === 1 ? "" : "s"}
          <button type="button" onClick={onEdit} className="edit-link">edit</button>
        </span>
      </div>
      {threads.length > 0 ? (
        <div className="x-thread-list">
          {threads.map((thread) => <XThreadPreview key={thread.tweet_id} thread={thread} />)}
        </div>
      ) : (
        <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)", padding: "6px 0" }}>
          No author threads linked yet.
        </div>
      )}
    </div>
  );
}

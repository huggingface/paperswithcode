import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { Check, Link2, Lock, Plus } from 'lucide-react';
import { PaperFeedList, type PaperFeedCard } from '@/components/PaperFeed';
import { PaperDateFilter } from '@/components/PaperDateFilter';
import { Skeleton } from '@/components/ui/skeleton';
import { usePaperFeedQuery } from '@/hooks/usePapers';
import { researchApi, TOPIC_PAPERS_PAGE_SIZE, type PublicTopic, type TopicPaperOrder, type TopicPerson } from '@/lib/api/research';
import { readHomepagePaperDateRange, withHomepagePaperDateRange } from '@/lib/paperDateRange';
import { researchQueryKeys } from '@/lib/api/queryKeys';
import { hfLoginUrl, isAuthDisabled } from '@/lib/apiUrl';
import { useOptionalAuth } from '@/lib/authContext';
import { ApiError } from '@/lib/apiTransport';
import {
  readPendingTopicFollow, stashPendingTopicFollow, topicPath, topicTitle, useFollowTopic, useRemoveTopics,
} from '@/lib/researchTopic';
import { transformPaperForCard } from '@/lib/transform';

/** A public free-text topic: who made it, who follows it, and the papers a model matched to it. */
export default function TopicView() {
  const { topicParam = '' } = useParams();
  const topicId = Number.parseInt(topicParam, 10);
  const user = useOptionalAuth()?.user;
  const subject = user?.hf_subject;
  // Sort and date range live in the URL like the homepage feed; a topic shows the last month by default.
  const [searchParams, setSearchParams] = useSearchParams();
  const order: TopicPaperOrder = searchParams.get('order') === 'newest' ? 'newest' : 'trending';
  const dateRange = readHomepagePaperDateRange(searchParams, undefined, 'month');
  const showOrder = (value: TopicPaperOrder) => {
    const next = new URLSearchParams(searchParams);
    if (value === 'newest') next.set('order', value);
    else next.delete('order');
    setSearchParams(next);
  };
  const topic = useQuery({
    queryKey: researchQueryKeys.publicTopic(topicId, subject),
    queryFn: () => researchApi.publicTopic(topicId),
    enabled: Number.isInteger(topicId) && topicId > 0,
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  });
  const papers = usePaperFeedQuery(
    researchQueryKeys.topicPapers(topicId, order, dateRange, subject),
    async (offset) => {
      const results = await researchApi.topicPapers(topicId, order, offset, dateRange);
      return { results, next_page: results.length === TOPIC_PAPERS_PAGE_SIZE ? offset + TOPIC_PAPERS_PAGE_SIZE : null };
    },
    { enabled: topic.isSuccess, initialPage: 0 },
  );
  const cards = useMemo<PaperFeedCard[]>(
    () => papers.data?.pages.flatMap(page => page.results.map(transformPaperForCard)) ?? [],
    [papers.data],
  );
  useTopicHead(topic.data);

  if (topic.error || !(topicId > 0)) {
    return <div className="page topic-page">
      <h1 className="feed-title">Topic not found</h1>
      <p className="topic-description">This topic does not exist or its creator made it private.</p>
      <p><Link to="/">Back to trending research</Link></p>
    </div>;
  }
  if (!topic.data) return <div className="page topic-page" aria-busy="true">
    <div className="feed-header"><div>
      <Skeleton className="h-3 w-16 mb-3" />
      <Skeleton className="h-10 w-80 max-w-full" />
    </div></div>
    <div className="layout-with-sidebar">
      <aside className="sidebar topic-sidebar">
        <Skeleton className="h-8 w-40 mb-6" />
        <Skeleton className="h-9 w-full" />
      </aside>
      <div className="feed-main">
        <PaperFeedList query={papers} isLoading cards={[]} skeleton="card" empty={null} />
      </div>
    </div>
  </div>;
  const data = topic.data;
  const title = topicTitle(data);
  return <div className="page topic-page">
    <div className="feed-header">
      <div>
        <span className="topic-kicker">Topic</span>
        <h1 className="feed-title">{title}</h1>
        {data.text.toLowerCase() !== title.toLowerCase() && <p className="topic-description">{data.text}</p>}
      </div>
    </div>
    <div className="layout-with-sidebar">
      <aside className="sidebar topic-sidebar">
        {!data.is_public && <p className="topic-private"><Lock aria-hidden="true" />Private: only you and existing followers can open this page.</p>}
        {data.creator && <div className="sidebar-section">
          <div className="sidebar-label">Created by</div>
          <a className="topic-creator" href={`https://huggingface.co/${data.creator.username}`} target="_blank" rel="noreferrer">
            <Avatar person={data.creator} size={32} /><span className="topic-creator-name">@{data.creator.username}</span>
          </a>
        </div>}
        <div className="sidebar-section">
          <div className="sidebar-label">Followers</div>
          <div className="topic-followers">
            {data.follower_avatars.length > 0 && <span className="topic-follower-avatars">
              {data.follower_avatars.map(p => <Avatar key={p.username} person={p} size={26} />)}
            </span>}
            <span>{data.followers === 1 ? '1 person follows this topic' : `${data.followers.toLocaleString()} people follow this topic`}</span>
          </div>
        </div>
        <div className="sidebar-section topic-actions">
          <FollowTopicButton topic={data} />
          <ShareButton path={topicPath(data)} />
        </div>
      </aside>
      <div className="feed-main">
        <div className="sort-bar home-feed-sort-bar">
          <div className="paper-feed-toolbar-controls">
            <div className="sort-options">
              {(['trending', 'newest'] as const).map(value => <button key={value} type="button"
                className={`sort-btn ${order === value ? 'active' : ''}`} onClick={() => showOrder(value)}>{value}</button>)}
            </div>
          </div>
          <PaperDateFilter startDate={dateRange.startDate} endDate={dateRange.endDate}
            onChange={value => setSearchParams(withHomepagePaperDateRange(searchParams, value))} />
        </div>
        {(data.status === 'pending' || data.status === 'running') && <p className="following-topic-note" role="status">
          Showing the closest papers now. A model is reading papers to refine these matches, which takes a few minutes.
        </p>}
        <PaperFeedList query={papers} cards={cards} skeleton="card" rootMargin="400px"
          empty={papers.error ? 'Could not load papers for this topic.'
            : dateRange.startDate || dateRange.endDate ? 'No papers about this topic in this window.' : 'No papers match this topic yet.'} />
      </div>
    </div>
  </div>;
}

function Avatar({ person, size }: { person: TopicPerson; size: number }) {
  return <img className="topic-avatar" src={person.avatar_url} alt="" title={`@${person.username}`}
    width={size} height={size} loading="lazy" />;
}

/** Sets the tab title and keeps thin or hidden topics out of search engines. */
function useTopicHead(topic: PublicTopic | undefined) {
  useEffect(() => {
    if (!topic) return;
    const priorTitle = document.title;
    document.title = `${topicTitle(topic)} — Papers With Code topics`;
    let robots = document.querySelector<HTMLMetaElement>('meta[name="robots"]');
    const created = !robots;
    if (!robots) {
      robots = document.createElement('meta');
      robots.name = 'robots';
      document.head.appendChild(robots);
    }
    const priorRobots = robots.content;
    if (!topic.indexable) robots.content = 'noindex, follow';
    return () => {
      document.title = priorTitle;
      if (created) robots.remove();
      else robots.content = priorRobots;
    };
  }, [topic]);
}

function FollowTopicButton({ topic }: { topic: PublicTopic }) {
  const auth = useOptionalAuth();
  const user = auth?.user;
  const follow = useFollowTopic();
  const remove = useRemoveTopics();
  // A guest who pressed Follow comes back signed in: finish the follow once.
  const resumed = useRef(false);
  useEffect(() => {
    if (!user || resumed.current || readPendingTopicFollow() !== topic.id) return;
    resumed.current = true;
    if (topic.following) return;
    follow.mutate(topic.id);
  }, [user, topic.id, topic.following, follow]);
  if (!auth || (!user && isAuthDisabled())) return null;
  if (!user) return <a className="research-follow-btn" href={hfLoginUrl(topicPath(topic))}
    onClick={() => stashPendingTopicFollow(topic.id)}>
    <Plus aria-hidden="true" />Follow
  </a>;
  const busy = follow.isPending || remove.isPending;
  const error = follow.error ?? remove.error;
  return <>
    <button type="button" className={topic.following ? 'research-follow-btn is-following' : 'research-follow-btn'}
      disabled={busy} aria-pressed={topic.following}
      onClick={() => topic.following ? remove.mutate([topic.id]) : follow.mutate(topic.id)}>
      {topic.following ? <>
        <Check aria-hidden="true" />
        <span className="research-follow-label">Following</span>
        <span className="research-follow-label-hover">Unfollow</span>
      </> : <><Plus aria-hidden="true" />Follow</>}
    </button>
    {error && <span className="research-follow-hint is-error" role="alert">
      {error instanceof ApiError && error.status === 409 ? 'You follow the maximum number of topics. Remove one in Settings first.' : 'Could not update this topic. Please try again.'}
    </span>}
  </>;
}

function ShareButton({ path }: { path: string }) {
  const [copied, setCopied] = useState(false);
  return <button type="button" className="topic-secondary-btn" onClick={() => {
    void navigator.clipboard?.writeText(`${window.location.origin}${path}`).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    });
  }}>
    <Link2 aria-hidden="true" />{copied ? 'Link copied' : 'Share'}
  </button>;
}

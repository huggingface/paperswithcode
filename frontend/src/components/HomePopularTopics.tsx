import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowRight, Check, ChevronLeft, ChevronRight, Plus, Users } from 'lucide-react';
import TopicCard, { FollowCard } from '@/components/TopicCard';
import { researchQueries } from '@/lib/api/queries';
import { TOPIC_LIMIT, type PopularFollow, type TopicBubble } from '@/lib/api/research';
import { displayTaskName } from '@/lib/transform';
import {
  FEATURED_TOPIC_COUNT, homeTopics, topicTitle, useFollowFeaturedEntity, useFollowFeaturedTopic,
} from '@/lib/researchTopic';

type Item = { kind: 'topic'; topic: TopicBubble; followers: number }
  | { kind: 'task' | 'method'; follow: PopularFollow; followers: number };

const KIND_LABELS = { topic: 'Topic', task: 'Task', method: 'Method' } as const;
// Ties keep tasks before methods before topics.
const KIND_ORDER = { task: 0, method: 1, topic: 2 } as const;

const followKey = (follow: PopularFollow) => `${follow.kind}:${follow.entity_id}`;

/** The most followed tasks, methods and public topics, a few of each, as one horizontally scrolling row of cards
 * above the trending feed, most followed first, so visitors discover following. `followedIds` marks topics and
 * `followedKeys` the `kind:id` of tasks and methods the account already follows; either is null while that is
 * unknown: the cards paint at once and their buttons wait. `onBuild` opens the Edit feed pop-up. */
export default function HomePopularTopics({ followedIds, followedKeys, onBuild }: {
  followedIds: ReadonlySet<number> | null;
  followedKeys: ReadonlySet<string> | null;
  onBuild: () => void;
}) {
  const featured = useQuery(researchQueries.featuredTopics());
  const popular = useQuery(researchQueries.popularFollows());
  const { follow, finishing, failed } = useFollowFeaturedTopic();
  const entity = useFollowFeaturedEntity();
  const topics = homeTopics(featured.data ?? []).slice(0, FEATURED_TOPIC_COUNT);
  const items: Item[] = [
    ...(popular.data ?? []).map(entry => ({ kind: entry.kind, follow: entry, followers: entry.followers })),
    ...topics.map(topic => ({ kind: 'topic' as const, topic, followers: topic.followers })),
  ].sort((a, b) => b.followers - a.followers || KIND_ORDER[a.kind] - KIND_ORDER[b.kind]);
  const followEntity = (entry: PopularFollow) => entity.follow(
    entry.kind, entry.entity_id, entry.kind === 'task' ? displayTaskName(entry.name) : entry.name);
  const atLimit = (followedIds?.size ?? 0) >= TOPIC_LIMIT;
  const list = useRef<HTMLUListElement>(null);
  const [edges, setEdges] = useState({ start: true, end: true });
  useEffect(() => {
    const row = list.current;
    if (!row) return;
    const update = () => setEdges({
      start: row.scrollLeft <= 1,
      end: row.scrollLeft + row.clientWidth >= row.scrollWidth - 1,
    });
    update();
    row.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    return () => {
      row.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, [items.length]);
  // One page is the visible cards plus the gap after them, so the next card lands at the start.
  const page = (direction: 1 | -1) => {
    const row = list.current;
    if (!row) return;
    const gap = parseFloat(getComputedStyle(row).columnGap) || 0;
    row.scrollBy({ left: direction * (row.clientWidth + gap), behavior: 'smooth' });
  };
  if (items.length === 0) return null;

  function topicAction(topic: TopicBubble) {
    if (!followedIds) return <span className="home-topic-follow is-pending" aria-hidden="true"><Plus />Follow</span>;
    if (followedIds.has(topic.id)) {
      return <Link to={`/following?topic=${topic.id}`} className="home-topic-follow is-following">
        <Check aria-hidden="true" />Following
      </Link>;
    }
    return <button
      type="button"
      className="home-topic-follow"
      disabled={finishing || entity.pending || atLimit}
      title={atLimit ? `You follow ${TOPIC_LIMIT} topics, the most allowed. Remove one to add another.` : undefined}
      onClick={() => follow(topic.id)}
      aria-label={`Follow ${topicTitle(topic)}`}
    >
      <Plus aria-hidden="true" />Follow
    </button>;
  }

  function entityAction(entry: PopularFollow) {
    if (!followedKeys) return <span className="home-topic-follow is-pending" aria-hidden="true"><Plus />Follow</span>;
    if (followedKeys.has(followKey(entry))) {
      return <Link to={`/following?follow=${followKey(entry)}`} className="home-topic-follow is-following">
        <Check aria-hidden="true" />Following
      </Link>;
    }
    return <button
      type="button"
      className="home-topic-follow"
      disabled={finishing || entity.pending}
      onClick={() => followEntity(entry)}
      aria-label={`Follow ${entry.kind === 'task' ? displayTaskName(entry.name) : entry.name}`}
    >
      <Plus aria-hidden="true" />Follow
    </button>;
  }

  return <section className="home-topics" aria-labelledby="home-topics-title">
    <div className="home-topics-header">
      <h2 id="home-topics-title"><Users aria-hidden="true" />Most followed</h2>
      <div className="home-topics-actions">
        <button type="button" className="home-topics-own" onClick={onBuild}>
          Create your own topic<ArrowRight aria-hidden="true" />
        </button>
        {!(edges.start && edges.end) && <>
          <button type="button" className="home-topics-page" aria-label="Previous cards" disabled={edges.start}
            onClick={() => page(-1)}>
            <ChevronLeft aria-hidden="true" />
          </button>
          <button type="button" className="home-topics-page" aria-label="More cards" disabled={edges.end}
            onClick={() => page(1)}>
            <ChevronRight aria-hidden="true" />
          </button>
        </>}
      </div>
    </div>
    <ul ref={list} className="home-topics-list is-scroller">
      {items.map(item => item.kind === 'topic'
        ? <TopicCard key={`topic:${item.topic.id}`} topic={item.topic} kindLabel={KIND_LABELS.topic}
          action={topicAction(item.topic)} />
        : <FollowCard
          key={followKey(item.follow)}
          title={item.kind === 'task' ? displayTaskName(item.follow.name) : item.follow.name}
          href={item.follow.url}
          kindLabel={KIND_LABELS[item.kind]}
          followers={item.follow.followers}
          avatars={item.follow.follower_avatars}
          weekPapers={item.follow.week_papers}
          paper={item.follow.top_paper}
          action={entityAction(item.follow)}
        />)}
    </ul>
    {(failed || entity.failed) && <p className="home-topics-error" role="alert">
      Could not follow that. Please try again.
    </p>}
  </section>;
}

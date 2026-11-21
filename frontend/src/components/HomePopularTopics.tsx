import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowRight, Check, ChevronLeft, ChevronRight, Plus, Users } from 'lucide-react';
import TopicCard from '@/components/TopicCard';
import { researchQueries } from '@/lib/api/queries';
import { TOPIC_LIMIT } from '@/lib/api/research';
import { FEATURED_TOPIC_COUNT, topicTitle, useFollowFeaturedTopic } from '@/lib/researchTopic';

/** The most followed public topics as a horizontally scrolling row of cards above the trending feed, so visitors
 * discover following. `followedIds` marks topics the account already follows, or is null while that is unknown: the
 * cards paint at once and their buttons wait. `onBuild` opens the Edit feed pop-up. */
export default function HomePopularTopics({ followedIds, onBuild }: {
  followedIds: ReadonlySet<number> | null;
  onBuild: () => void;
}) {
  const featured = useQuery(researchQueries.featuredTopics());
  const { follow, finishing, failed } = useFollowFeaturedTopic();
  const topics = (featured.data ?? []).slice(0, FEATURED_TOPIC_COUNT);
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
  }, [topics.length]);
  // One page is the visible cards plus the gap after them, so the next card lands at the start.
  const page = (direction: 1 | -1) => {
    const row = list.current;
    if (!row) return;
    const gap = parseFloat(getComputedStyle(row).columnGap) || 0;
    row.scrollBy({ left: direction * (row.clientWidth + gap), behavior: 'smooth' });
  };
  if (topics.length === 0) return null;

  return <section className="home-topics" aria-labelledby="home-topics-title">
    <div className="home-topics-header">
      <h2 id="home-topics-title"><Users aria-hidden="true" />Popular topics to follow</h2>
      <div className="home-topics-actions">
        <button type="button" className="home-topics-own" onClick={onBuild}>
          Follow your own topic<ArrowRight aria-hidden="true" />
        </button>
        {!(edges.start && edges.end) && <>
          <button type="button" className="home-topics-page" aria-label="Previous topics" disabled={edges.start}
            onClick={() => page(-1)}>
            <ChevronLeft aria-hidden="true" />
          </button>
          <button type="button" className="home-topics-page" aria-label="More topics" disabled={edges.end}
            onClick={() => page(1)}>
            <ChevronRight aria-hidden="true" />
          </button>
        </>}
      </div>
    </div>
    <ul ref={list} className="home-topics-list is-scroller">
      {topics.map(topic => <TopicCard key={topic.id} topic={topic} action={!followedIds
        ? <span className="home-topic-follow is-pending" aria-hidden="true"><Plus />Follow</span>
        : followedIds.has(topic.id)
        ? <Link to={`/following?topic=${topic.id}`} className="home-topic-follow is-following">
          <Check aria-hidden="true" />Following
        </Link>
        : <button
          type="button"
          className="home-topic-follow"
          disabled={finishing || atLimit}
          title={atLimit ? `You follow ${TOPIC_LIMIT} topics, the most allowed. Remove one to add another.` : undefined}
          onClick={() => follow(topic.id)}
          aria-label={`Follow ${topicTitle(topic)}`}
        >
          <Plus aria-hidden="true" />Follow
        </button>} />)}
    </ul>
    {failed && <p className="home-topics-error" role="alert">Could not follow that topic. Please try again.</p>}
  </section>;
}

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowRight, Check, Plus, Users } from 'lucide-react';
import TopicCard from '@/components/TopicCard';
import { researchQueries } from '@/lib/api/queries';
import { FEATURED_TOPIC_COUNT, topicTitle, useFollowFeaturedTopic } from '@/lib/researchTopic';

/** The most followed public topics as cards above the trending feed, so visitors discover following.
 * `followedIds` marks topics the account already follows; `onBuild` opens the Edit feed pop-up. */
export default function HomePopularTopics({ followedIds, onBuild }: {
  followedIds: ReadonlySet<number>;
  onBuild: () => void;
}) {
  const featured = useQuery(researchQueries.featuredTopics());
  const { follow, finishing, failed } = useFollowFeaturedTopic();
  const topics = (featured.data ?? []).slice(0, FEATURED_TOPIC_COUNT);
  if (topics.length === 0) return null;

  return <section className="home-topics" aria-labelledby="home-topics-title">
    <div className="home-topics-header">
      <h2 id="home-topics-title"><Users aria-hidden="true" />Popular topics to follow</h2>
      <button type="button" className="home-topics-own" onClick={onBuild}>
        Follow your own topic<ArrowRight aria-hidden="true" />
      </button>
    </div>
    <ul className="home-topics-list">
      {topics.map(topic => <TopicCard key={topic.id} topic={topic} action={followedIds.has(topic.id)
        ? <Link to={`/following?topic=${topic.id}`} className="home-topic-follow is-following">
          <Check aria-hidden="true" />Following
        </Link>
        : <button
          type="button"
          className="home-topic-follow"
          disabled={finishing}
          onClick={() => follow(topic.id)}
          aria-label={`Follow ${topicTitle(topic)}`}
        >
          <Plus aria-hidden="true" />Follow
        </button>} />)}
    </ul>
    {failed && <p className="home-topics-error" role="alert">Could not follow that topic. Please try again.</p>}
  </section>;
}

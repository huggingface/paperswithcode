import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowRight, Check, Plus, Users } from 'lucide-react';
import { researchQueries } from '@/lib/api/queries';
import { assetUrl } from '@/lib/apiUrl';
import type { TopicPerson } from '@/lib/api/research';
import { FEATURED_TOPIC_COUNT, topicPath, topicTitle, useFollowFeaturedTopic } from '@/lib/researchTopic';

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
      {topics.map(topic => {
        const following = followedIds.has(topic.id);
        const avatars = topic.follower_avatars ?? [];
        const paper = topic.top_paper;
        return <li key={topic.id} className="home-topic-card">
          <Link to={topicPath(topic)} className="home-topic-title">{topicTitle(topic)}</Link>
          <div className="home-topic-followers">
            {avatars.length > 0 && <span className="home-topic-avatars" aria-hidden="true">
              {avatars.map(person => <FollowerAvatar key={person.username} person={person} />)}
            </span>}
            {topic.followers} {topic.followers === 1 ? 'follower' : 'followers'}
          </div>
          {!!topic.week_papers && <div className="home-topic-meta">
            {topic.week_papers} new {topic.week_papers === 1 ? 'paper' : 'papers'} this week
          </div>}
          {paper && <Link to={`/paper/${paper.arxiv_id || paper.id}`} className="home-topic-paper" title={paper.title}>
            {paper.title}
          </Link>}
          {following
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
            </button>}
        </li>;
      })}
    </ul>
    {failed && <p className="home-topics-error" role="alert">Could not follow that topic. Please try again.</p>}
  </section>;
}

/** A follower's face, or their initial when the image does not load. */
function FollowerAvatar({ person }: { person: TopicPerson }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return <span className="topic-avatar home-topic-avatar-initial">{person.username.charAt(0).toUpperCase()}</span>;
  }
  return <img
    className="topic-avatar"
    src={assetUrl(person.avatar_url) ?? undefined}
    alt=""
    width={20}
    height={20}
    loading="lazy"
    onError={() => setFailed(true)}
  />;
}

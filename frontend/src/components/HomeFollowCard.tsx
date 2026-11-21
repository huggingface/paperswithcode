import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Plus, Sparkles, X } from 'lucide-react';
import { researchQueries } from '@/lib/api/queries';
import { FEATURED_TOPIC_COUNT, topicTitle, useFollowFeaturedTopic } from '@/lib/researchTopic';

const DISMISSED_KEY = 'pwc:home-follow-card:dismissed';
const TOPIC_COUNT = 5;

function readDismissed() {
  try {
    return localStorage.getItem(DISMISSED_KEY) === '1';
  } catch {
    return false;
  }
}

/** Invites guests and accounts without follows, inside the trending feed, to build a following feed.
 * A popular topic follows in one click (guests sign in first); `onBuild` opens the Edit feed pop-up. */
export default function HomeFollowCard({ onBuild }: { onBuild: () => void }) {
  const featured = useQuery(researchQueries.featuredTopics());
  const { follow, finishing, failed } = useFollowFeaturedTopic();
  const [dismissed, setDismissed] = useState(readDismissed);
  if (dismissed) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(DISMISSED_KEY, '1');
    } catch {
      // Without storage the card simply returns on the next visit.
    }
    setDismissed(true);
  };
  // The popular topics row above the feed already offers the first few.
  const topics = (featured.data ?? []).slice(FEATURED_TOPIC_COUNT, FEATURED_TOPIC_COUNT + TOPIC_COUNT);

  return <section className="home-follow-card" aria-labelledby="home-follow-card-title">
    <button type="button" className="home-follow-card-close" aria-label="Dismiss" onClick={dismiss}>
      <X aria-hidden="true" />
    </button>
    <h2 id="home-follow-card-title">Get a feed for your research</h2>
    <p>
      Follow topics, tasks, authors and labs, and their new papers collect on your following page
      and in a weekly email.
    </p>
    {topics.length > 0 && <div className="topic-dialog-chips home-follow-card-topics">
      {topics.map(topic => <button
        key={topic.id}
        type="button"
        className="topic-dialog-chip"
        aria-pressed="false"
        disabled={finishing}
        onClick={() => follow(topic.id)}
      >
        <Plus aria-hidden="true" />{topicTitle(topic)}
      </button>)}
    </div>}
    {failed && <p className="home-follow-card-error" role="alert">
      Could not follow that topic. Please try again.
    </p>}
    <button type="button" className="research-topic-save" onClick={onBuild}>
      <Sparkles aria-hidden="true" />Build your feed
    </button>
  </section>;
}

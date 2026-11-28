import { useState } from 'react';
import { Plus, Sparkles, X } from 'lucide-react';
import { useFollowFeaturedEntity, useFollowFeaturedTopic } from '@/lib/researchTopic';

const DISMISSED_KEY = 'pwc:home-follow-card:dismissed';

type Pick = { kind: 'topic' | 'task' | 'method'; id: number; name: string };

/** Hand-picked topics, tasks and methods that show a newcomer what a feed can follow. */
const HOME_FOLLOW_PICKS: Pick[] = [
  { kind: 'method', id: 1004, name: 'Recursive Self-Improvement' },
  { kind: 'topic', id: 23, name: 'OCR releases' },
  { kind: 'topic', id: 51, name: 'Small language models (<4B)' },
  { kind: 'task', id: 862, name: 'Auto-Research' },
  { kind: 'method', id: 1048, name: 'Decision Models' },
  { kind: 'task', id: 438, name: 'Deep Research Agents' },
];

function readDismissed() {
  try {
    return localStorage.getItem(DISMISSED_KEY) === '1';
  } catch {
    return false;
  }
}

/** Invites guests and accounts without follows, inside the trending feed, to build a following feed.
 * A hand-picked topic, task or method follows in one click (guests sign in first); `onBuild` opens the Edit feed
 * pop-up. */
export default function HomeFollowCard({ onBuild }: { onBuild: () => void }) {
  const topic = useFollowFeaturedTopic();
  const entity = useFollowFeaturedEntity();
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
  const follow = (pick: Pick) => pick.kind === 'topic'
    ? topic.follow(pick.id)
    : entity.follow(pick.kind, pick.id, pick.name);

  return <section className="home-follow-card" aria-labelledby="home-follow-card-title">
    <button type="button" className="home-follow-card-close" aria-label="Dismiss" onClick={dismiss}>
      <X aria-hidden="true" />
    </button>
    <h2 id="home-follow-card-title">Get a feed for your research</h2>
    <p>
      Follow topics, tasks, authors and labs, and their new papers collect on your following page
      and in a weekly email.
    </p>
    <div className="topic-dialog-chips home-follow-card-topics">
      {HOME_FOLLOW_PICKS.map(pick => <button
        key={`${pick.kind}:${pick.id}`}
        type="button"
        className="topic-dialog-chip"
        aria-pressed="false"
        disabled={topic.finishing || entity.pending}
        onClick={() => follow(pick)}
      >
        <Plus aria-hidden="true" />{pick.name}
      </button>)}
    </div>
    {(topic.failed || entity.failed) && <p className="home-follow-card-error" role="alert">
      Could not follow that. Please try again.
    </p>}
    <button type="button" className="research-topic-save" onClick={onBuild}>
      <Sparkles aria-hidden="true" />Build your feed
    </button>
  </section>;
}

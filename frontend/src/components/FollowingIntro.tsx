import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { useAuth } from '@/lib/authContext';
import { isAuthDisabled } from '@/lib/apiUrl';
import { readPendingFollows, readPendingTopic } from '@/lib/researchTopic';
import TopicDialog from './TopicDialog';

/** Invites guests and accounts without follows to build their feed on /following.
 * `openTopic` opens the pop-up on arrival, unless a guest's picks are still waiting to be saved after sign-in. */
export default function FollowingIntro({ openTopic = false }: { openTopic?: boolean }) {
  const { user } = useAuth();
  const canFollowTopic = !!user || !isAuthDisabled();
  const [topicOpen, setTopicOpen] = useState(
    () => openTopic && canFollowTopic && !readPendingTopic() && !readPendingFollows().length);
  return <section className="following-intro" aria-labelledby="following-intro-title">
    <h2 id="following-intro-title">Build your personal research feed</h2>
    <p className="following-intro-lead">
      Describe a topic in your own words, or follow the tasks, benchmarks, authors, and
      organizations you care about, and this page collects their latest papers and results in
      one place.
    </p>
    {canFollowTopic && <>
      <button type="button" className="research-topic-save following-intro-topic" onClick={() => setTopicOpen(true)}>
        <Sparkles aria-hidden="true" />Build your feed
      </button>
      <TopicDialog open={topicOpen} onOpenChange={setTopicOpen} />
    </>}
    <p className="following-intro-note">
      Matching papers also arrive as a weekly email, which you can turn off in{' '}
      <Link to="/settings">Settings</Link>.
    </p>
  </section>;
}

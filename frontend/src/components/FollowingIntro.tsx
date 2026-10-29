import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import type { Task } from '@/lib/api/catalog.types';
import { displayTaskName } from '@/lib/transform';
import { useAuth } from '@/lib/authContext';
import { isAuthDisabled } from '@/lib/apiUrl';
import { readPendingTopic } from '@/lib/researchTopic';
import TopicDialog from './TopicDialog';

/** Asks for a topic on /following, shown to guests and to accounts without follows.
 * The topic pop-up opens on arrival; guests sign in on submit, and /following saves the topic when they return. */
export default function FollowingIntro({ popularTasks = [] }: { popularTasks?: Task[] }) {
  const { user } = useAuth();
  const canFollowTopic = !!user || !isAuthDisabled();
  const [topicOpen, setTopicOpen] = useState(() => canFollowTopic && !readPendingTopic());
  return <section className="following-intro" aria-labelledby="following-intro-title">
    <h2 id="following-intro-title">Build your personal research feed</h2>
    <p className="following-intro-lead">
      Describe a topic in your own words, or follow the tasks, benchmarks, authors, and
      organizations you care about, and this page collects their latest papers and results in
      one place.
    </p>
    {canFollowTopic && <>
      <button type="button" className="research-topic-save following-intro-topic" onClick={() => setTopicOpen(true)}>
        <Sparkles aria-hidden="true" />Follow a topic
      </button>
      <TopicDialog open={topicOpen} onOpenChange={setTopicOpen} signInToSave />
    </>}
    <p className="following-intro-note">
      Matching papers also arrive as a weekly email, which you can turn off in{' '}
      <Link to="/settings">Settings</Link>.
    </p>
    {popularTasks.length > 0 && <div className="following-intro-popular">
      <h3>Popular tasks to follow</h3>
      <div>
        {popularTasks.map(task => <Link key={task.id} to={`/tasks/${task.slug}`}>{displayTaskName(task.name, task.slug)}</Link>)}
      </div>
    </div>}
  </section>;
}

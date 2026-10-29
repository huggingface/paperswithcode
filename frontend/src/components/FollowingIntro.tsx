import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import type { Task } from '@/lib/api/catalog.types';
import { TOPIC_MAX_LENGTH } from '@/lib/api/research';
import { displayTaskName } from '@/lib/transform';
import { hfLoginUrl } from './HfSignInButton';
import { savePendingTopic, useSaveTopic } from '@/lib/researchTopic';

/** Asks for a topic on /following, shown to guests and to accounts without follows.
 * Guests sign in on submit, and /following saves the topic when they return. */
export default function FollowingIntro({ signedIn, popularTasks = [] }: { signedIn: boolean; popularTasks?: Task[] }) {
  const [draft, setDraft] = useState('');
  const save = useSaveTopic();
  const trimmed = draft.trim().replace(/\s+/g, ' ');
  const submittable = trimmed.length >= 3 && !save.isPending;
  const submit = () => {
    if (!submittable) return;
    if (signedIn) {
      save.mutate(trimmed);
      return;
    }
    savePendingTopic(trimmed);
    window.location.href = hfLoginUrl('/following');
  };
  return <section className="following-intro" aria-labelledby="following-intro-title">
    <h2 id="following-intro-title">Build your personal research feed</h2>
    <p className="following-intro-lead">
      Describe a topic in your own words, or follow the tasks, benchmarks, authors, and
      organizations you care about, and this page collects their latest papers and results in
      one place.
    </p>
    <form className="following-intro-topic" onSubmit={event => { event.preventDefault(); submit(); }}>
      <textarea rows={3} maxLength={TOPIC_MAX_LENGTH} aria-label="Research topic"
        placeholder="e.g. speculative decoding for LLM inference"
        value={draft} onChange={event => setDraft(event.target.value)}
        onKeyDown={event => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }} />
      <button type="submit" disabled={!submittable}>Follow topic<ArrowRight aria-hidden="true" /></button>
    </form>
    {save.error && <p className="settings-token-error" role="alert">Could not save your topic. Please try again.</p>}
    <p className="following-intro-note">
      Matching papers appear here and in a weekly email, which you can turn off in{' '}
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

import { Link } from 'react-router-dom';
import { Building2, FlaskConical, ListChecks, Mail, Plus } from 'lucide-react';
import type { Task } from '@/lib/api/catalog.types';
import { displayTaskName } from '@/lib/transform';
import HfSignInButton from './HfSignInButton';

/** Explains how to start following, shown on /following to guests and to accounts without follows. */
export default function FollowingIntro({ signedIn, popularTasks = [] }: { signedIn: boolean; popularTasks?: Task[] }) {
  const steps = [
    ...(signedIn ? [] : [<>Sign in with your Hugging Face account. Your follows stay private.</>]),
    <>Describe the research you care about in your own words in{' '}
      {signedIn ? <Link to="/settings#topic">Settings</Link> : 'Settings'}, or open any task, method,
      benchmark, author, or organization page and click{' '}
      <span className="following-intro-pill"><Plus aria-hidden="true" />Follow</span>.</>,
    <>New papers matching your topic and everything you follow appear here, ranked like the
      trending feed. You can also get them as a weekly email from <Link to="/settings">Settings</Link>.</>,
  ];
  return <section className="following-intro" aria-labelledby="following-intro-title">
    <h2 id="following-intro-title">Build your personal research feed</h2>
    <p className="following-intro-lead">
      Describe a topic in your own words, or follow the tasks, benchmarks, authors, and
      organizations you care about, and this page collects their latest papers and results in
      one place.
    </p>
    <ol className="following-intro-steps">
      {steps.map((step, index) => <li key={index}><span aria-hidden="true">{index + 1}</span><p>{step}</p></li>)}
    </ol>
    {!signedIn && <div className="following-intro-signin"><HfSignInButton returnTo="/following" label="Sign in to start following" /></div>}
    <div className="following-intro-browse">
      <Link to="/tasks"><ListChecks aria-hidden="true" />Browse tasks</Link>
      <Link to="/methods"><FlaskConical aria-hidden="true" />Browse methods</Link>
      <Link to="/organizations"><Building2 aria-hidden="true" />Browse organizations</Link>
      {signedIn && <Link to="/settings"><Mail aria-hidden="true" />Weekly email</Link>}
    </div>
    {popularTasks.length > 0 && <div className="following-intro-popular">
      <h3>Popular tasks to follow</h3>
      <div>
        {popularTasks.map(task => <Link key={task.id} to={`/tasks/${task.slug}`}>{displayTaskName(task.name, task.slug)}</Link>)}
      </div>
    </div>}
  </section>;
}

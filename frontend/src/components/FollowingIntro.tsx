import { Link } from 'react-router-dom';
import { Sparkles } from 'lucide-react';

/** Invites guests and accounts without follows to build their feed on /following.
 * `onBuild` opens the pop-up; without it, as when sign-in is disabled, there is no button. */
export default function FollowingIntro({ onBuild }: { onBuild?: () => void }) {
  return <section className="following-intro" aria-labelledby="following-intro-title">
    <h2 id="following-intro-title">Build your personal research feed</h2>
    <p className="following-intro-lead">
      Describe a topic in your own words, or follow the tasks, benchmarks, authors, and
      organizations you care about, and this page collects their latest papers and results in
      one place.
    </p>
    {onBuild && <button type="button" className="research-topic-save following-intro-topic" onClick={onBuild}>
      <Sparkles aria-hidden="true" />Build your feed
    </button>}
    <p className="following-intro-note">
      Matching papers also arrive as a weekly email, which you can turn off in{' '}
      <Link to="/settings">Settings</Link>.
    </p>
  </section>;
}

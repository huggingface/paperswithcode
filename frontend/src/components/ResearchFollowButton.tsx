import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Check, Plus } from 'lucide-react';
import type { FollowKind } from '@/lib/api/research';
import { hfLoginUrl, isAuthDisabled } from '@/lib/apiUrl';
import { useOptionalAuth } from '@/lib/authContext';
import { useResearchFollows, useSetFollow } from '@/lib/researchTopic';

const HINTS: Record<FollowKind, string> = {
  task: 'Get new papers on this task',
  method: 'Get new papers using this method',
  benchmark: 'Get new results on this benchmark',
  author: 'Get new papers by this author',
  organization: 'Get new papers from this organization',
};

export default function ResearchFollowButton({ kind, entityId }: { kind: FollowKind; entityId: string | number }) {
  const auth = useOptionalAuth();
  const user = auth?.user;
  const location = useLocation();
  // Keyed by entity so a reused instance never confirms a follow on another page.
  const [justFollowed, setJustFollowed] = useState<string | null>(null);
  const entityKey = `${kind}:${entityId}`;
  const follows = useResearchFollows();
  const followed = follows.data?.some(f => f.kind === kind && String(f.entity_id) === String(entityId)) ?? false;
  // Stay disabled until the refreshed follows say which way the button points.
  const mutation = useSetFollow({ onChanged: ({ follow }) => setJustFollowed(follow ? entityKey : null), awaitRefresh: true });
  if (!auth) return null;
  if (!user && isAuthDisabled()) return null;
  if (!user) return <div className="research-follow">
    <a className="research-follow-btn" href={hfLoginUrl(location.pathname + location.search)}>
      <Plus aria-hidden="true" />Follow
    </a>
    <span className="research-follow-hint">Sign in to {HINTS[kind].toLowerCase()}.</span>
  </div>;
  const failed = mutation.error || follows.error;
  return <div className="research-follow">
    <button type="button" className={followed ? 'research-follow-btn is-following' : 'research-follow-btn'}
      disabled={follows.isLoading || !!follows.error || mutation.isPending}
      aria-pressed={followed} aria-label={followed ? 'Unfollow' : 'Follow'} onClick={() => mutation.mutate({ kind, entityId, follow: !followed })}>
      {followed ? <>
        <Check aria-hidden="true" />
        <span className="research-follow-label">Following</span>
        <span className="research-follow-label-hover">Unfollow</span>
      </> : <><Plus aria-hidden="true" />Follow</>}
    </button>
    {failed ? <span className="research-follow-hint is-error" role="alert">Could not update follows. Please try again.</span>
      : followed ? justFollowed === entityKey && <span className="research-follow-hint" role="status">
        Added to <Link to="/following">your Following feed</Link>
        {' · '}<Link to="/settings">Manage in Settings</Link>
      </span>
      : <span className="research-follow-hint">{HINTS[kind]} in <Link to="/following">your Following feed</Link>.</span>}
  </div>;
}

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useLocation } from 'react-router-dom';
import { Check, Plus } from 'lucide-react';
import { researchApi, type FollowKind } from '@/lib/api/research';
import { useOptionalAuth } from '@/lib/authContext';
import { hfLoginUrl } from './HfSignInButton';

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
  const client = useQueryClient();
  const [justFollowed, setJustFollowed] = useState(false);
  const queryKey = ['research-follows', user?.hf_subject];
  const follows = useQuery({ queryKey, queryFn: researchApi.follows, enabled: !!user });
  const followed = follows.data?.some(f => f.kind === kind && String(f.entity_id) === String(entityId)) ?? false;
  const mutation = useMutation({
    mutationFn: () => researchApi.setFollow(kind, entityId, !followed),
    onSuccess: async () => {
      setJustFollowed(!followed);
      await client.invalidateQueries({ queryKey });
      await client.invalidateQueries({ queryKey: ['research-feed', user?.hf_subject] });
    },
  });
  if (!auth) return null;
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
      aria-pressed={followed} aria-label={followed ? 'Unfollow' : 'Follow'} onClick={() => mutation.mutate()}>
      {followed ? <>
        <Check aria-hidden="true" />
        <span className="research-follow-label">Following</span>
        <span className="research-follow-label-hover">Unfollow</span>
      </> : <><Plus aria-hidden="true" />Follow</>}
    </button>
    {failed ? <span className="research-follow-hint is-error" role="alert">Could not update follows. Please try again.</span>
      : followed ? justFollowed && <span className="research-follow-hint" role="status">
        Added to <Link to="/following">your Following feed</Link>.
      </span>
      : <span className="research-follow-hint">{HINTS[kind]} in <Link to="/following">your Following feed</Link>.</span>}
  </div>;
}

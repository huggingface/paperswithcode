import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocation } from 'react-router-dom';
import { researchApi, type FollowKind } from '@/lib/api/research';
import { useOptionalAuth } from '@/lib/authContext';
import HfSignInButton from './HfSignInButton';
import { Button } from './ui/button';

export default function ResearchFollowButton({ kind, entityId }: { kind: FollowKind; entityId: string | number }) {
  const auth = useOptionalAuth();
  const user = auth?.user;
  const location = useLocation();
  const client = useQueryClient();
  const queryKey = ['research-follows', user?.hf_subject];
  const follows = useQuery({ queryKey, queryFn: researchApi.follows, enabled: !!user });
  const followed = follows.data?.some(f => f.kind === kind && String(f.entity_id) === String(entityId)) ?? false;
  const mutation = useMutation({
    mutationFn: () => researchApi.setFollow(kind, entityId, !followed),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey });
      await client.invalidateQueries({ queryKey: ['research-feed', user?.hf_subject] });
    },
  });
  if (!auth) return null;
  if (!user) return <HfSignInButton returnTo={location.pathname + location.search} label="Sign in to follow" />;
  return <div className="my-3">
    <Button variant="outline" size="sm" disabled={follows.isLoading || !!follows.error || mutation.isPending}
      aria-pressed={followed} onClick={() => mutation.mutate()}>{followed ? 'Unfollow' : 'Follow'}</Button>
    {(mutation.error || follows.error) && <p role="alert">Could not update follows. Please try again.</p>}
  </div>;
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { researchApi } from '@/lib/api/research';
import { useAuth } from '@/lib/authContext';
import HfSignInButton from './HfSignInButton';
import ResearchFollowButton from './ResearchFollowButton';
import { Switch } from './ui/switch';

export default function ResearchSettings() {
  const { user } = useAuth();
  const client = useQueryClient();
  const follows = useQuery({ queryKey: ['research-follows', user?.hf_subject], queryFn: researchApi.follows, enabled: !!user });
  const emailKey = ['research-email', user?.hf_subject];
  const email = useQuery({ queryKey: emailKey, queryFn: researchApi.email, enabled: !!user });
  const update = useMutation({ mutationFn: researchApi.setEmail, onSuccess: data => client.setQueryData(emailKey, data) });
  return <section className="settings-section">
    <h2 className="settings-section-title">Research follows &amp; weekly email</h2>
    <p>Your follows are private. <Link to="/following">Open your Following feed</Link>.</p>
    {!user ? <HfSignInButton returnTo="/settings" /> : <>
      {(follows.isLoading || email.isLoading) && <p>Loading research preferences…</p>}
      {(follows.error || email.error) && <p role="alert">Could not load research preferences.</p>}
      {email.data && <div className="my-4">
        <div className="flex items-center justify-between gap-4">
          <label htmlFor="research-weekly-email">Weekly research email · Mondays at 08:00 UTC</label>
          <Switch id="research-weekly-email" checked={email.data.enabled}
            disabled={update.isPending || (!email.data.enabled && (!email.data.email || email.data.suppressed))}
            onCheckedChange={enabled => update.mutate(enabled)} />
        </div>
        {email.data.email && <p className="mt-2">Destination: {email.data.email}</p>}
        <HfSignInButton returnTo="/settings" collectEmail label={email.data.email ? 'Refresh verified email access' : 'Allow verified email access'} />
        {email.data.suppressed && <p>Delivery to this address is suppressed after a bounce or complaint.</p>}
        {!email.data.delivery_ready && <p>Email delivery is not available yet. You can save your preference now.</p>}
        {update.error && <p role="alert">Could not save your preference. Refresh verified email access and try again.</p>}
      </div>}
      {follows.data?.length === 0 && <p>Follow tasks, methods, benchmarks, authors, or organizations from their pages.</p>}
      <ul>{follows.data?.map(f => <li key={`${f.kind}:${f.entity_id}`} className="flex flex-wrap items-center justify-between gap-3">
        <span><Link to={f.url}>{f.name}</Link> <small>({f.kind})</small></span>
        <ResearchFollowButton kind={f.kind} entityId={f.entity_id} />
      </li>)}</ul>
    </>}
  </section>;
}

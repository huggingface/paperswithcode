import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowRight, Building2, FlaskConical, ListChecks, Mail, Trophy, User, type LucideIcon } from 'lucide-react';
import { researchApi, type FollowKind, type ResearchFollow } from '@/lib/api/research';
import { useAuth } from '@/lib/authContext';
import HfSignInButton, { hfLoginUrl } from './HfSignInButton';
import { Switch } from './ui/switch';
import TopicSettings from './TopicSettings';

const KINDS: { kind: FollowKind; label: string; icon: LucideIcon; browse?: string }[] = [
  { kind: 'task', label: 'Tasks', icon: ListChecks, browse: '/tasks' },
  { kind: 'method', label: 'Methods', icon: FlaskConical, browse: '/methods' },
  { kind: 'benchmark', label: 'Benchmarks', icon: Trophy },
  { kind: 'author', label: 'Authors', icon: User },
  { kind: 'organization', label: 'Organizations', icon: Building2, browse: '/organizations' },
];
const followKey = (f: Pick<ResearchFollow, 'kind' | 'entity_id'>) => `${f.kind}:${f.entity_id}`;
const since = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });

function FollowList({ follows }: { follows: ResearchFollow[] }) {
  const { user } = useAuth();
  const client = useQueryClient();
  // Unfollowed rows stay until the page is left, so a misclick can be undone in place.
  const [unfollowed, setUnfollowed] = useState<ResearchFollow[]>([]);
  const change = useMutation({
    mutationFn: ({ follow, enabled }: { follow: ResearchFollow; enabled: boolean }) =>
      researchApi.setFollow(follow.kind, follow.entity_id, enabled),
    onSuccess: (_, { follow, enabled }) => {
      // Update the cached list in the same render as `unfollowed` so a row never flips state late.
      const queryKey = ['research-follows', user?.hf_subject];
      client.setQueryData<ResearchFollow[]>(queryKey, current => enabled
        ? [...(current ?? []), follow]
        : (current ?? []).filter(f => followKey(f) !== followKey(follow)));
      setUnfollowed(rows => [
        ...rows.filter(r => followKey(r) !== followKey(follow)),
        ...(enabled ? [] : [follow]),
      ]);
      void client.invalidateQueries({ queryKey });
      void client.invalidateQueries({ queryKey: ['research-feed', user?.hf_subject] });
    },
  });
  const active = new Set(follows.map(followKey));
  const rows = [...follows, ...unfollowed.filter(f => !active.has(followKey(f)))];
  if (!rows.length) return <EmptyFollows />;
  return <>
    {KINDS.map(({ kind, label, icon: Icon }) => {
      const group = rows.filter(f => f.kind === kind).sort((a, b) => a.name.localeCompare(b.name));
      if (!group.length) return null;
      return <div key={kind} className="research-follow-group">
        <h3 className="research-follow-group-title"><Icon aria-hidden="true" />{label}</h3>
        <ul className="research-follow-list">{group.map(f => {
          const following = active.has(followKey(f));
          return <li key={followKey(f)} className={following ? 'research-follow-row' : 'research-follow-row is-unfollowed'}>
            <div className="research-follow-text">
              <Link to={f.url}>{f.name}</Link>
              <span>{following ? `Following since ${since(f.created_at)}` : 'Unfollowed'}</span>
            </div>
            <button type="button" className={following ? 'research-follow-action' : 'research-follow-action is-refollow'}
              disabled={change.isPending} aria-label={`${following ? 'Unfollow' : 'Follow'} ${f.name}`}
              onClick={() => change.mutate({ follow: f, enabled: !following })}>
              {following ? 'Unfollow' : 'Follow again'}
            </button>
          </li>;
        })}</ul>
      </div>;
    })}
    {change.error && <p className="settings-token-error" role="alert">Could not update follows. Please try again.</p>}
  </>;
}

function EmptyFollows() {
  return <div className="research-follow-empty">
    <p><strong>You are not following any tasks, methods, benchmarks, authors, or organizations yet.</strong></p>
    <p>Use the Follow button on any task, method, benchmark, author, or organization page.</p>
    <div className="research-follow-browse">
      {KINDS.filter(k => k.browse).map(({ kind, label, icon: Icon, browse }) =>
        <Link key={kind} to={browse!}><Icon aria-hidden="true" />Browse {label.toLowerCase()}</Link>)}
    </div>
  </div>;
}

export default function ResearchSettings() {
  const { user } = useAuth();
  const client = useQueryClient();
  const follows = useQuery({ queryKey: ['research-follows', user?.hf_subject], queryFn: researchApi.follows, enabled: !!user });
  const emailKey = ['research-email', user?.hf_subject];
  const email = useQuery({ queryKey: emailKey, queryFn: researchApi.email, enabled: !!user });
  const update = useMutation({ mutationFn: researchApi.setEmail, onSuccess: data => client.setQueryData(emailKey, data) });
  const count = follows.data?.length ?? 0;
  const prefs = email.data;
  const canOptIn = !!prefs?.email && !prefs.suppressed;
  return <>
    <section className="settings-section" aria-labelledby="research-following-heading">
      <div className="research-section-heading">
        <h2 className="settings-section-title" id="research-following-heading">
          Following{count > 0 && <span className="research-follow-count">{count}</span>}
        </h2>
        {user && <Link className="research-feed-link" to="/following">Open Following feed <ArrowRight aria-hidden="true" /></Link>}
      </div>
      <p className="settings-row-desc research-section-intro">
        New papers and benchmark results from your topic and what you follow appear in your
        Following feed. Your topic and follows are private.
      </p>
      {!user ? <div className="settings-note">
        <span>Sign in to follow research and build your personal feed.</span>
        <div className="settings-note-action"><HfSignInButton returnTo="/settings" /></div>
      </div> : follows.isLoading ? <p className="settings-billing-loading">Loading follows…</p>
        : follows.error ? <p className="settings-token-error" role="alert">Could not load your follows.</p>
        : <><TopicSettings /><FollowList follows={follows.data ?? []} /></>}
    </section>

    {user && <section className="settings-section" aria-labelledby="research-email-heading">
      <h2 className="settings-section-title" id="research-email-heading">Weekly research email</h2>
      {email.isLoading ? <p className="settings-billing-loading">Loading email preferences…</p>
        : email.error || !prefs ? <p className="settings-token-error" role="alert">Could not load email preferences.</p>
        : <>
        <div className="settings-row">
          <label className="settings-row-text" htmlFor="research-weekly-email">
            <span className="settings-row-label">Email me a weekly digest</span>
            <span className="settings-row-desc">
              Up to 20 new papers and benchmark results matching your follows, sent
              Mondays at 08:00 UTC. No email is sent in weeks without new matches. On by
              default once you follow something; turn it off here or from any email.
            </span>
          </label>
          <Switch id="research-weekly-email" checked={prefs.enabled}
            disabled={update.isPending || (!prefs.enabled && !canOptIn)}
            onCheckedChange={enabled => update.mutate(enabled)} />
        </div>
        <div className="research-email-destination">
          <Mail aria-hidden="true" />
          {prefs.email ? <>
            <span>Sending to <strong>{prefs.email}</strong></span>
            <a href={hfLoginUrl('/settings', false, true)}>Refresh from Hugging Face</a>
          </> : <>
            <span>To receive it, allow access to the verified email on your Hugging Face account.</span>
            <HfSignInButton returnTo="/settings" collectEmail label="Allow email access" />
          </>}
        </div>
        {prefs.suppressed && <p className="research-email-status is-warning" role="status">
          Delivery to this address is paused after a bounce or spam complaint.
        </p>}
        {!prefs.delivery_ready && <p className="research-email-status" role="status">
          Weekly emails have not launched yet. Your preference is saved and applies from launch.
        </p>}
        {update.error && <p className="settings-token-error" role="alert">
          Could not save your preference. Refresh your email from Hugging Face and try again.
        </p>}
      </>}
    </section>}
  </>;
}

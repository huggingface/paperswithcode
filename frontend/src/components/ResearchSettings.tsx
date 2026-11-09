import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowRight, Mail } from 'lucide-react';
import { researchApi } from '@/lib/api/research';
import { researchQueries } from '@/lib/api/queries';
import { useAuth } from '@/lib/authContext';
import { useResearchFollows, useResearchTopics } from '@/lib/researchTopic';
import { hfLoginUrl } from '@/lib/apiUrl';
import HfSignInButton from './HfSignInButton';
import { Switch } from './ui/switch';

export default function ResearchSettings() {
  const { user } = useAuth();
  const client = useQueryClient();
  const follows = useResearchFollows();
  const topics = useResearchTopics();
  const emailQuery = researchQueries.email(user?.hf_subject);
  const emailKey = emailQuery.queryKey;
  const email = useQuery({ ...emailQuery, enabled: !!user });
  const update = useMutation({ mutationFn: researchApi.setEmail, onSuccess: data => client.setQueryData(emailKey, data) });
  const showAsFollower = useMutation({
    mutationFn: async (show: boolean) => {
      await researchApi.setShowAsFollower(show);
      return show;
    },
    onSuccess: show => client.setQueryData<typeof email.data>(emailKey, current => current && { ...current, show_as_follower: show }),
  });
  const count = (follows.data?.length ?? 0) + (topics.data?.length ?? 0);
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
        New papers and benchmark results from your topics and what you follow appear in your
        Following feed. Your follows of tasks, methods, benchmarks, authors, and organizations are private.
      </p>
      {!user ? <div className="settings-note">
        <span>Sign in to follow research and build your personal feed.</span>
        <div className="settings-note-action"><HfSignInButton returnTo="/settings" /></div>
      </div> : <div className="settings-row">
        <span className="settings-row-text">
          <span className="settings-row-label">Topics and follows</span>
          <span className="settings-row-desc">
            Add, reword, reorder, unfollow, or make topics private in one place, the Edit feed pop-up on Following.
          </span>
        </span>
        <Link className="research-feed-link" to="/following?edit=1">Edit feed <ArrowRight aria-hidden="true" /></Link>
      </div>}
      {user && prefs && <div className="settings-row">
        <label className="settings-row-text" htmlFor="research-show-as-follower">
          <span className="settings-row-label">Show my avatar on topics I follow</span>
          <span className="settings-row-desc">
            Public topic pages show the avatars of some followers. Turn this off to be counted without your avatar.
          </span>
        </label>
        <Switch id="research-show-as-follower" checked={prefs.show_as_follower} disabled={showAsFollower.isPending}
          onCheckedChange={show => showAsFollower.mutate(show)} />
      </div>}
      {showAsFollower.error && <p className="settings-token-error" role="alert">Could not save your preference. Please try again.</p>}
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
            <a href={hfLoginUrl('/settings', { collectEmail: true })}>Refresh from Hugging Face</a>
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

import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useLocation } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { researchApi, TOPIC_MAX_LENGTH, type FollowKind, type ResearchTopic } from '@/lib/api/research';
import { useAuth } from '@/lib/authContext';
import { isAuthDisabled } from '@/lib/apiUrl';
import { stashPendingTopic, useSaveTopic } from '@/lib/researchTopic';
import { hfLoginUrl } from './HfSignInButton';

const KIND_NAMES: Record<FollowKind, string> = {
  task: 'task', method: 'method', benchmark: 'benchmark', author: 'author', organization: 'organization',
};

function topicStatus(topic: ResearchTopic): string {
  if (topic.status === 'failed') return 'We could not finish finding papers for this topic. Save it again to retry.';
  if (topic.status === 'done') return 'Matching papers appear in your Following feed, and new ones are added every hour.';
  return topic.total ? `Your feed shows the closest papers now. Refining matches: ${topic.judged.toLocaleString()} of ${topic.total.toLocaleString()} checked…`
    : 'Your feed shows the closest papers now. Refining matches…';
}

/** One free-text research topic; Jev decides which papers match it.
 * `onDone` makes it the editor inside TopicDialog, which closes after a save, removal, or cancel.
 * `signInToSave` also shows it to guests, who sign in on submit; /following saves the topic on return. */
export default function TopicSettings({ onDone, signInToSave = false }: { onDone?: () => void; signInToSave?: boolean }) {
  const { user } = useAuth();
  const location = useLocation();
  const input = useRef<HTMLInputElement>(null);
  const queryKey = ['research-topic', user?.hf_subject];
  const topic = useQuery({
    queryKey,
    queryFn: researchApi.topic,
    enabled: !!user,
    // Poll while the backfill runs so progress and the first matches show up.
    refetchInterval: query => query.state.data && ['pending', 'running'].includes(query.state.data.status) ? 5000 : false,
  });
  const [draft, setDraft] = useState<string | null>(null);
  const save = useSaveTopic(() => {
    setDraft(null);
    onDone?.();
  });
  const inline = !!onDone;
  useEffect(() => {
    if ((inline || location.hash === '#topic') && topic.isSuccess) {
      if (!inline) input.current?.scrollIntoView({ block: 'center' });
      input.current?.focus();
    }
  }, [inline, location.hash, topic.isSuccess]);
  if (!user && (!signInToSave || isAuthDisabled())) return null;
  const saved = topic.data?.text ?? '';
  const value = draft ?? saved;
  const trimmed = value.trim().replace(/\s+/g, ' ');
  // Saving the same text again restarts a backfill that gave up.
  const retry = topic.data?.status === 'failed' && trimmed === saved;
  const savable = trimmed.length >= 3 && (trimmed !== saved || retry);
  const submit = () => {
    if (!savable || save.isPending) return;
    if (user) {
      save.mutate(trimmed);
      return;
    }
    stashPendingTopic(trimmed);
    window.location.href = hfLoginUrl(`${location.pathname}${location.search}`);
  };
  return <div className="research-topic" id="topic">
    {!inline && <h3 className="research-follow-group-title"><Sparkles aria-hidden="true" />Topic</h3>}
    <p className="settings-row-desc">
      Describe the research you want to follow in your own words, for example
      {' '}<em>real-time video generation</em> or <em>speculative decoding for LLM inference</em>.
      A model reads every new paper and adds the ones that match to your Following feed.
    </p>
    {topic.isLoading ? <p className="settings-billing-loading">Loading your topic…</p>
      : topic.error ? <p className="settings-token-error" role="alert">Could not load your topic.</p>
      : <form className="research-topic-form" onSubmit={event => {
          event.preventDefault();
          submit();
        }}>
        <div className="research-topic-field">
          <input ref={input} className="research-topic-input" type="text" maxLength={TOPIC_MAX_LENGTH}
            aria-label="Research topic" placeholder="e.g. diffusion policies for robot manipulation"
            value={value} onChange={event => setDraft(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.nativeEvent.isComposing) {
                event.preventDefault();
                submit();
              }
            }} />
          <button type="submit" className="research-topic-save"
            disabled={save.isPending || !savable}>
            {retry ? 'Retry' : saved ? 'Update topic' : 'Follow topic'}
          </button>
        </div>
        {(value || onDone || saved) && <div className="research-topic-actions">
          {value && <span className="research-topic-count">{value.length}/{TOPIC_MAX_LENGTH}</span>}
          {onDone && <button type="button" className="research-follow-action" disabled={save.isPending}
            onClick={() => { setDraft(null); onDone(); }}>Cancel</button>}
          {saved && <button type="button" className="research-follow-action" disabled={save.isPending}
            onClick={() => save.mutate(null)}>Remove</button>}
        </div>}
      </form>}
    {topic.data && <p className="research-email-status" role="status">{topicStatus(topic.data)}</p>}
    {topic.data?.suggestions.map(s => <p key={`${s.kind}:${s.entity_id}`} className="research-topic-suggestion">
      <Link to={s.url}>{s.name}</Link> is a {KIND_NAMES[s.kind]} in the catalog. Following it as well adds
      every paper tagged with it.
    </p>)}
    {save.error && <p className="settings-token-error" role="alert">Could not save your topic. Please try again.</p>}
  </div>;
}

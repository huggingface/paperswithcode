import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { TOPIC_LIMIT, TOPIC_MAX_LENGTH, type FollowKind, type ResearchTopic } from '@/lib/api/research';
import { useAuth } from '@/lib/authContext';
import { looksLikeTopicList, topicPath, topicTitle, useRemoveTopics, useReorderTopics, useResearchTopics, useSaveTopic, useSetTopicPublic } from '@/lib/researchTopic';
import SortableList from './SortableList';
import { Switch } from './ui/switch';

const KIND_NAMES: Record<FollowKind, string> = {
  task: 'task', method: 'method', benchmark: 'benchmark', author: 'author', organization: 'organization',
};

function topicStatus(topic: ResearchTopic): string {
  if (topic.status === 'failed') return 'We could not finish finding papers for this topic. Save it again to retry.';
  if (topic.status === 'done') return 'Matching papers appear in your Following feed, and new ones are added every hour.';
  return topic.total ? `Your feed shows the closest papers now. Refining matches: ${topic.judged.toLocaleString()} of ${topic.total.toLocaleString()} checked…`
    : 'Your feed shows the closest papers now. Refining matches…';
}

/** Free-text research topics, each judged by Jev; TopicDialog edits the same topics on /following. */
export default function TopicSettings() {
  const { user } = useAuth();
  const location = useLocation();
  const section = useRef<HTMLDivElement>(null);
  const topics = useResearchTopics();
  const reorder = useReorderTopics();
  useEffect(() => {
    if (location.hash === '#topic' && topics.isSuccess) {
      const input = section.current?.querySelector('textarea');
      input?.scrollIntoView({ block: 'center' });
      input?.focus();
    }
  }, [location.hash, topics.isSuccess]);
  if (!user) return null;
  const list = topics.data ?? [];
  return <div className="research-topic" id="topic" ref={section}>
    <h3 className="research-follow-group-title"><Sparkles aria-hidden="true" />Topics</h3>
    <p className="settings-row-desc">
      Describe the research you want to follow in your own words, for example
      {' '}<em>real-time video generation</em> or <em>speculative decoding for LLM inference</em>.
      A model reads every new paper and adds the ones that match to your Following feed.
      You can follow up to {TOPIC_LIMIT} topics. New topics are public: anyone can open and follow them, and
      they show your Hugging Face username.
    </p>
    {topics.isLoading ? <p className="settings-billing-loading">Loading your topics…</p>
      : topics.error ? <p className="settings-token-error" role="alert">Could not load your topics.</p>
      : <>
        <SortableList className="research-topic-list" items={list} itemKey={topic => topic.id}
          itemLabel={topic => topicTitle(topic)} disabled={reorder.isPending}
          onReorder={order => reorder.mutate(order)}
          renderItem={(topic, handle) => <TopicEditor topic={topic} handle={handle} />} />
        {reorder.error && <p className="settings-token-error" role="alert">Could not save the new order. Please try again.</p>}
        {list.length < TOPIC_LIMIT && <TopicEditor key={`new-${list.length}`} />}
      </>}
  </div>;
}

/** Edits one followed topic, or without `topic` adds a new one. */
function TopicEditor({ topic, handle }: { topic?: ResearchTopic; handle?: ReactNode }) {
  const [draft, setDraft] = useState<string | null>(null);
  const save = useSaveTopic(() => setDraft(null));
  const remove = useRemoveTopics();
  const saved = topic?.text ?? '';
  const value = draft ?? saved;
  const trimmed = value.trim().replace(/\s+/g, ' ');
  // Saving the same text again restarts a backfill that gave up.
  const retry = topic?.status === 'failed' && trimmed === saved;
  const savable = trimmed.length >= 3 && (trimmed !== saved || retry);
  const busy = save.isPending || remove.isPending;
  const submit = () => {
    if (savable && !busy) save.mutate({ id: topic?.id, text: trimmed });
  };
  return <div className={handle ? 'research-topic-item has-handle' : 'research-topic-item'}>
    {handle}
    <div className="research-topic-body">
    <form className="research-topic-form" onSubmit={event => {
      event.preventDefault();
      submit();
    }}>
      <textarea className="research-topic-input" rows={topic ? 2 : 3} maxLength={TOPIC_MAX_LENGTH}
        aria-label={topic ? 'Research topic' : 'New research topic'}
        placeholder={topic ? undefined : 'e.g. diffusion policies for robot manipulation'}
        value={value} onChange={event => setDraft(event.target.value)}
        onKeyDown={event => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }} />
      <div className="research-topic-actions">
        <span className="research-topic-count">{value.length}/{TOPIC_MAX_LENGTH}</span>
        {topic && <button type="button" className="research-follow-action" disabled={busy}
          onClick={() => remove.mutate([topic.id])}>Remove</button>}
        <button type="submit" className="research-topic-save" disabled={busy || !savable}>
          {retry ? 'Retry' : topic ? 'Update topic' : 'Follow topic'}
        </button>
      </div>
    </form>
    {!topic && looksLikeTopicList(value) && <p className="research-topic-suggestion">
      Tip: this lists several areas. Add each one as its own topic for better matches.
    </p>}
    {topic && <p className="research-email-status" role="status">{topicStatus(topic)}</p>}
    {topic && <TopicSharing topic={topic} />}
    {topic?.suggestions.map(s => <p key={`${s.kind}:${s.entity_id}`} className="research-topic-suggestion">
      <Link to={s.url}>{s.name}</Link> is a {KIND_NAMES[s.kind]} in the catalog. Following it as well adds
      every paper tagged with it.
    </p>)}
    {(save.error || remove.error) && <p className="settings-token-error" role="alert">
      Could not save your topic. Please try again.
    </p>}
    </div>
  </div>;
}

/** The topic page link, and for its creator the public/private switch. */
function TopicSharing({ topic }: { topic: ResearchTopic }) {
  const visibility = useSetTopicPublic();
  const switchId = `topic-public-${topic.id}`;
  return <div className="research-topic-sharing">
    <Link to={topicPath(topic)}>Topic page</Link>
    {topic.is_creator ? <>
      <label htmlFor={switchId}>Public</label>
      <Switch id={switchId} checked={topic.is_public} disabled={visibility.isPending}
        onCheckedChange={isPublic => visibility.mutate({ id: topic.id, isPublic })} />
      <span className="research-topic-sharing-note">
        {topic.is_public ? 'Anyone can open and follow it; it shows your username.' : 'Only you and existing followers can open it.'}
      </span>
    </> : <span className="research-topic-sharing-note">
      {topic.is_public ? 'Created by another account.' : 'Private topic created by another account.'}
    </span>}
    {visibility.error && <span className="settings-token-error" role="alert">Could not change this topic. Please try again.</span>}
  </div>;
}

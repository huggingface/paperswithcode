import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useLocation } from 'react-router-dom';
import { ArrowRight, Check, Plus } from 'lucide-react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { catalogApi } from '@/lib/api/catalog';
import { researchApi, TOPIC_MAX_LENGTH, type FollowKind } from '@/lib/api/research';
import { useAuth } from '@/lib/authContext';
import { displayTaskName } from '@/lib/transform';
import { stashPendingFollows, stashPendingTopic, useSaveFollows, useSaveTopic, type FollowPick } from '@/lib/researchTopic';
import { hfLoginUrl } from './HfSignInButton';

// Well-known researchers; author popularity has no data signal, since citation ranks favour coauthors of a few huge papers.
const POPULAR_AUTHORS = [
  { id: '266', name: 'Yann LeCun' },
  { id: '4049', name: 'Jürgen Schmidhuber' },
  { id: '13379', name: 'Geoffrey Hinton' },
  { id: '25', name: 'Yoshua Bengio' },
  { id: '264', name: 'Kaiming He' },
];
// Suggested chips per group, after everything already followed; each group links to its full listing for more.
const CHIPS_PER_GROUP = 5;

/** Builds the Following feed in a pop-up, so /following shows no input field next to the chat box:
 * a free-text topic plus trending tasks and methods, popular authors, and organizations to follow. Guests sign in on submit, and
 * /following saves what they picked when they return. */
export default function TopicDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="topic-dialog" aria-describedby={undefined}>
      <TopicDialogForm onDone={() => onOpenChange(false)} />
    </DialogContent>
  </Dialog>;
}

function TopicDialogForm({ onDone }: { onDone: () => void }) {
  const { user } = useAuth();
  const location = useLocation();
  const topic = useQuery({ queryKey: ['research-topic', user?.hf_subject], queryFn: researchApi.topic, enabled: !!user });
  const follows = useQuery({ queryKey: ['research-follows', user?.hf_subject], queryFn: researchApi.follows, enabled: !!user });
  const tasks = useQuery({
    queryKey: ['trending-tasks-sidebar'],
    queryFn: () => catalogApi.trendingTasks({ limit: 8, level: 0 }),
    staleTime: 10 * 60 * 1000,
  });
  const methods = useQuery({
    queryKey: ['trending-methods-follow'],
    queryFn: () => catalogApi.trendingMethods({ limit: CHIPS_PER_GROUP }),
    staleTime: 10 * 60 * 1000,
  });
  const organizations = useQuery({
    queryKey: ['organizations', 'featured'],
    queryFn: () => catalogApi.organizationIndex(),
    staleTime: 10 * 60 * 1000,
  });
  // The directory's curated order puts the best-known labs first.
  const popularOrganizations = (organizations.data?.results ?? [])
    .filter(org => org.display_order != null)
    .sort((a, b) => a.display_order! - b.display_order!);
  const [draft, setDraft] = useState<string | null>(null);
  // The follow state chosen per chip; submit sends only those that differ from the current follows,
  // so chips stay right when a partial save refreshes the follows.
  const [selection, setSelection] = useState<FollowPick[]>([]);
  const saveTopic = useSaveTopic();
  const saveFollows = useSaveFollows();
  const saved = topic.data?.text ?? '';
  const value = draft ?? saved;
  const trimmed = value.trim().replace(/\s+/g, ' ');
  // Saving the same text again restarts a backfill that gave up.
  const retry = topic.data?.status === 'failed' && trimmed === saved;
  const topicSavable = trimmed.length >= 3 && (trimmed !== saved || retry);
  const saving = saveTopic.isPending || saveFollows.isPending;
  const isFollowed = (kind: FollowKind, id: string) =>
    follows.data?.some(follow => follow.kind === kind && String(follow.entity_id) === id) ?? false;
  const isSelected = (kind: FollowKind, id: string) =>
    selection.find(pick => pick.kind === kind && pick.id === id)?.follow ?? isFollowed(kind, id);
  const changes = selection.filter(pick => pick.follow !== isFollowed(pick.kind, pick.id));
  const submittable = !saving && (topicSavable || changes.length > 0);
  const toggle = (kind: FollowKind, id: string, name: string) => setSelection(current => [
    ...current.filter(pick => pick.kind !== kind || pick.id !== id),
    { kind, id, name, follow: !isSelected(kind, id) },
  ]);
  const submit = () => {
    if (!submittable) return;
    if (!user) {
      if (topicSavable) stashPendingTopic(trimmed);
      if (changes.length) stashPendingFollows(changes);
      window.location.href = hfLoginUrl(`${location.pathname}${location.search}`);
      return;
    }
    // Save the follows and the topic independently, so one failing still saves the other.
    const saves = [
      ...(changes.length ? [saveFollows.mutateAsync(changes)] : []),
      ...(topicSavable ? [saveTopic.mutateAsync(trimmed)] : []),
    ];
    void Promise.allSettled(saves).then(results => {
      if (results.every(result => result.status === 'fulfilled')) onDone();
    });
  };
  // Each group lists what is already followed, then the top suggestions not followed yet.
  const chips = (
    title: string,
    kind: FollowKind,
    suggestions: { id: string; name: string; slug?: string | null }[],
    browse?: { to: string; label: string },
  ) => {
    const followed = (follows.data ?? []).filter(follow => follow.kind === kind)
      .map(follow => ({ id: String(follow.entity_id), name: follow.name, slug: follow.url.split('/').pop() }));
    const items = [
      ...followed,
      ...suggestions.filter(item => !isFollowed(kind, item.id)).slice(0, CHIPS_PER_GROUP),
    ];
    return items.length > 0 && <div className="topic-dialog-group">
      <h3>{title}</h3>
      <div className="topic-dialog-chips">
        {items.map(item => {
          const on = isSelected(kind, item.id);
          const name = kind === 'task' ? displayTaskName(item.name, item.slug ?? undefined) : item.name;
          return <button key={item.id} type="button" className="topic-dialog-chip" aria-pressed={on} disabled={saving}
            onClick={() => toggle(kind, item.id, name)}>
            {on ? <Check aria-hidden="true" /> : <Plus aria-hidden="true" />}{name}
          </button>;
        })}
        {browse && <Link to={browse.to} className="topic-dialog-browse">{browse.label}<ArrowRight aria-hidden="true" /></Link>}
      </div>
    </div>;
  };
  return <form className="topic-dialog-form" onSubmit={event => {
    event.preventDefault();
    submit();
  }}>
    <DialogTitle className="topic-dialog-title">
      {saved || follows.data?.length ? 'Edit your research feed' : 'Build your research feed'}
    </DialogTitle>
    <div className="topic-dialog-group">
      <h3><label htmlFor="topic-dialog-input">Describe a topic in your own words</label></h3>
      <p className="topic-dialog-hint">A model reads every new paper and adds the ones that match to your Following feed.</p>
      <textarea id="topic-dialog-input" className="research-topic-input" rows={4} maxLength={TOPIC_MAX_LENGTH}
        aria-label="Research topic"
        placeholder="e.g. diffusion policies for robot manipulation, or speculative decoding for LLM inference"
        value={value} onChange={event => setDraft(event.target.value)}
        onKeyDown={event => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }} />
      <span className="research-topic-count">{value.length}/{TOPIC_MAX_LENGTH}</span>
    </div>
    {chips('Trending tasks', 'task', tasks.data?.results ?? [], { to: '/tasks', label: 'Browse tasks' })}
    {chips('Trending methods', 'method', methods.data?.results ?? [], { to: '/methods', label: 'Browse methods' })}
    {chips('Benchmarks', 'benchmark', [], { to: '/tasks', label: 'Browse benchmarks' })}
    {chips('Popular authors', 'author', POPULAR_AUTHORS)}
    {chips('Popular organizations', 'organization', popularOrganizations,
      { to: '/organizations', label: 'Browse organizations' })}
    {(saveTopic.error || saveFollows.error) && <p className="settings-token-error" role="alert">
      Could not save your feed. Please try again.
    </p>}
    <div className="topic-dialog-actions">
      {saved && <button type="button" className="research-follow-action topic-dialog-remove" disabled={saving}
        onClick={() => saveTopic.mutate(null, { onSuccess: onDone })}>Remove topic</button>}
      <button type="button" className="research-follow-action" disabled={saving} onClick={onDone}>Cancel</button>
      <button type="submit" className="research-topic-save" disabled={!submittable}>
        {changes.some(change => change.follow === false) ? 'Save'
          : changes.length ? 'Follow' : retry ? 'Retry' : saved ? 'Update topic' : 'Follow'}
      </button>
    </div>
  </form>;
}

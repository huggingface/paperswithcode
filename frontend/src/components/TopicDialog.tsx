import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation } from 'react-router-dom';
import { Check, Plus } from 'lucide-react';
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
  { id: '1469', name: 'Fei-Fei Li' },
  { id: '3079', name: 'Ilya Sutskever' },
  { id: '219', name: 'Sergey Levine' },
  { id: '438', name: 'Percy Liang' },
  { id: '220', name: 'Chelsea Finn' },
];

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
    queryFn: () => catalogApi.trendingMethods({ limit: 8 }),
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
    .sort((a, b) => a.display_order! - b.display_order!)
    .slice(0, 10);
  const [draft, setDraft] = useState<string | null>(null);
  const [picks, setPicks] = useState<FollowPick[]>([]);
  const saveTopic = useSaveTopic();
  const saveFollows = useSaveFollows();
  const saved = topic.data?.text ?? '';
  const value = draft ?? saved;
  const trimmed = value.trim().replace(/\s+/g, ' ');
  const topicChanged = trimmed.length >= 3 && trimmed !== saved;
  const saving = saveTopic.isPending || saveFollows.isPending;
  const submittable = !saving && (topicChanged || picks.length > 0);
  const isPicked = (kind: FollowKind, id: string) => picks.some(pick => pick.kind === kind && pick.id === id);
  const isFollowed = (kind: FollowKind, id: string) =>
    follows.data?.some(follow => follow.kind === kind && String(follow.entity_id) === id) ?? false;
  const toggle = (pick: FollowPick) => setPicks(current => current.some(p => p.kind === pick.kind && p.id === pick.id)
    ? current.filter(p => p.kind !== pick.kind || p.id !== pick.id)
    : [...current, pick]);
  const submit = () => {
    if (!submittable) return;
    if (!user) {
      if (topicChanged) stashPendingTopic(trimmed);
      if (picks.length) stashPendingFollows(picks);
      window.location.href = hfLoginUrl(`${location.pathname}${location.search}`);
      return;
    }
    const finish = () => topicChanged ? saveTopic.mutate(trimmed, { onSuccess: onDone }) : onDone();
    if (picks.length) saveFollows.mutate(picks, { onSuccess: finish });
    else finish();
  };
  const chips = (title: string, kind: FollowKind, items: { id: string; name: string; slug?: string | null }[]) =>
    items.length > 0 && <div className="topic-dialog-group">
      <h3>{title}</h3>
      <div className="topic-dialog-chips">
        {items.map(item => {
          const followed = isFollowed(kind, item.id);
          const on = followed || isPicked(kind, item.id);
          const name = kind === 'task' ? displayTaskName(item.name, item.slug ?? undefined) : item.name;
          return <button key={item.id} type="button" className="topic-dialog-chip" aria-pressed={on}
            disabled={followed || saving} title={followed ? 'Already following' : undefined}
            onClick={() => toggle({ kind, id: item.id, name })}>
            {on ? <Check aria-hidden="true" /> : <Plus aria-hidden="true" />}{name}
          </button>;
        })}
      </div>
    </div>;
  return <form className="topic-dialog-form" onSubmit={event => {
    event.preventDefault();
    submit();
  }}>
    <DialogTitle className="topic-dialog-title">Build your research feed</DialogTitle>
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
    {chips('Trending tasks', 'task', tasks.data?.results ?? [])}
    {chips('Trending methods', 'method', methods.data?.results ?? [])}
    {chips('Popular authors', 'author', POPULAR_AUTHORS)}
    {chips('Popular organizations', 'organization', popularOrganizations)}
    {(saveTopic.error || saveFollows.error) && <p className="settings-token-error" role="alert">
      Could not save your feed. Please try again.
    </p>}
    <div className="topic-dialog-actions">
      {saved && <button type="button" className="research-follow-action topic-dialog-remove" disabled={saving}
        onClick={() => saveTopic.mutate(null, { onSuccess: onDone })}>Remove topic</button>}
      <button type="button" className="research-follow-action" disabled={saving} onClick={onDone}>Cancel</button>
      <button type="submit" className="research-topic-save" disabled={!submittable}>
        {saved && !picks.length ? 'Update topic' : 'Follow'}
      </button>
    </div>
  </form>;
}

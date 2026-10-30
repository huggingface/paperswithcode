import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useLocation } from 'react-router-dom';
import { ArrowRight, Check, Plus } from 'lucide-react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { catalogApi } from '@/lib/api/catalog';
import { hfLoginUrl } from '@/lib/apiUrl';
import { researchApi, TOPIC_MAX_LENGTH, type FollowKind, type FollowSuggestion } from '@/lib/api/research';
import { useAuth } from '@/lib/authContext';
import { displayTaskName } from '@/lib/transform';
import { researchQueryKeys, TEN_MINUTES } from '@/lib/api/queryKeys';
import { stashPendingFollows, stashPendingTopic, useResearchFollows, useSaveFollows, useSaveTopic, type FollowPick } from '@/lib/researchTopic';

// Suggestions fetched per group; each group shows as many as fit in two rows, after everything already followed,
// and links to its full listing for more.
const SUGGESTIONS_PER_GROUP = 16;

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
  const topic = useQuery({ queryKey: researchQueryKeys.topic(user?.hf_subject), queryFn: researchApi.topic, enabled: !!user });
  const follows = useResearchFollows();
  const tasks = useQuery({
    queryKey: ['trending-tasks-follow'],
    queryFn: () => catalogApi.trendingTasks({ limit: SUGGESTIONS_PER_GROUP, level: 0 }),
    staleTime: TEN_MINUTES,
  });
  const methods = useQuery({
    queryKey: ['trending-methods-follow'],
    queryFn: () => catalogApi.trendingMethods({ limit: SUGGESTIONS_PER_GROUP }),
    staleTime: TEN_MINUTES,
  });
  // Popular authors and the directory's top organizations, with faces and logos.
  const suggestions = useQuery({
    queryKey: ['research-follow-suggestions'],
    queryFn: researchApi.followSuggestions,
    staleTime: TEN_MINUTES,
  });
  const suggested = (items: FollowSuggestion[] = []) =>
    items.map(item => ({ id: String(item.entity_id), name: item.name, image: item.image_url }));
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
    suggestions: { id: string; name: string; slug?: string | null; image?: string | null }[],
    browse?: { to: string; label: string },
  ) => {
    const followed = (follows.data ?? []).filter(follow => follow.kind === kind).map(follow => ({
      id: String(follow.entity_id), name: follow.name, slug: follow.url.split('/').pop(), image: follow.image_url,
    }));
    const items = [
      ...followed,
      ...suggestions.filter(item => !isFollowed(kind, item.id)).map(item => ({ ...item, suggested: true })),
    ];
    return items.length > 0 && <div className="topic-dialog-group">
      <h3>{title}</h3>
      <TwoRowChips>
        {items.map(item => {
          const on = isSelected(kind, item.id);
          const name = kind === 'task' ? displayTaskName(item.name, item.slug ?? undefined) : item.name;
          return <button key={item.id} type="button" className="topic-dialog-chip" aria-pressed={on} disabled={saving}
            data-suggested={'suggested' in item || undefined} onClick={() => toggle(kind, item.id, name)}>
            {on ? <Check aria-hidden="true" /> : <Plus aria-hidden="true" />}
            {(kind === 'author' || kind === 'organization') && <ChipImage kind={kind} name={name} src={item.image} />}
            {name}
          </button>;
        })}
        {browse && <Link to={browse.to} className="topic-dialog-browse">{browse.label}<ArrowRight aria-hidden="true" /></Link>}
      </TwoRowChips>
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
    {chips('Popular authors', 'author', suggested(suggestions.data?.authors))}
    {chips('Popular organizations', 'organization', suggested(suggestions.data?.organizations),
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

/** Wraps chips, hiding trailing suggestions until followed chips, suggestions, and the browse link fit in two rows. */
function TwoRowChips({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const box = ref.current;
    if (!box) return;
    const fit = () => {
      const all = [...box.children] as HTMLElement[];
      const suggested = all.filter(element => element.dataset.suggested);
      suggested.forEach(element => { element.hidden = false; });
      const rows = () => new Set(all.filter(element => !element.hidden).map(element => element.offsetTop)).size;
      for (let i = suggested.length - 1; i >= 0 && rows() > 2; i--) suggested[i].hidden = true;
    };
    fit();
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  });
  return <div ref={ref} className="topic-dialog-chips">{children}</div>;
}

/** A face for authors and a logo for organizations; authors without a photo show their initials. */
function ChipImage({ kind, name, src }: { kind: 'author' | 'organization'; name: string; src?: string | null }) {
  const [failed, setFailed] = useState(false);
  if (src && !failed) {
    return <img className={`topic-dialog-chip-image is-${kind}`} src={src} alt="" loading="lazy"
      onError={() => setFailed(true)} />;
  }
  if (kind !== 'author') return null;
  const initials = name.split(/\s+/).filter(Boolean).map(part => part[0]).slice(0, 2).join('').toUpperCase();
  return <span className="topic-dialog-chip-image is-author is-initials" aria-hidden="true">{initials}</span>;
}

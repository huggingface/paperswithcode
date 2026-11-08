import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, Check, Plus } from 'lucide-react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { catalogApi } from '@/lib/api/catalog';
import { hfLoginUrl } from '@/lib/apiUrl';
import { researchApi, TOPIC_LIMIT, TOPIC_MAX_LENGTH, type FollowKind, type FollowSuggestion } from '@/lib/api/research';
import { useAuth } from '@/lib/authContext';
import { displayTaskName } from '@/lib/transform';
import { researchQueryKeys, TEN_MINUTES } from '@/lib/api/queryKeys';
import {
  stashPendingFollows, stashPendingTopic, topicTitle, useRemoveTopics, useResearchFollows, useResearchTopics, useSaveFollows, useSaveTopic,
  type FollowPick,
} from '@/lib/researchTopic';

// Suggestions fetched per group; each group shows as many as fit in two rows, after everything already followed,
// and links to its full listing for more.
const SUGGESTIONS_PER_GROUP = 16;

/** Builds the Following feed in a pop-up, so /following shows no input field next to the chat box:
 * a free-text topic (the one with `topicId`, or a new one) plus the other followed topics, trending tasks and methods,
 * popular authors, and organizations to follow. Guests sign in on submit, and /following saves what they picked when they return.
 * Opened elsewhere, `afterSavePath` (/following) is where a save leads and where guests return after signing in. */
export default function TopicDialog({ open, topicId = null, afterSavePath, onOpenChange }: {
  open: boolean;
  topicId?: number | null;
  afterSavePath?: string;
  onOpenChange: (open: boolean) => void;
}) {
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="topic-dialog" aria-describedby={undefined}>
      <TopicDialogForm key={topicId ?? 'new'} topicId={topicId} afterSavePath={afterSavePath} onDone={() => onOpenChange(false)} />
    </DialogContent>
  </Dialog>;
}

function TopicDialogForm({ topicId, afterSavePath, onDone }: {
  topicId: number | null;
  afterSavePath?: string;
  onDone: () => void;
}) {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const topics = useResearchTopics();
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
  // Other followed topics show as chips; unselecting one removes it on submit.
  const [removals, setRemovals] = useState<number[]>([]);
  const saveTopic = useSaveTopic();
  const removeTopics = useRemoveTopics();
  const saveFollows = useSaveFollows();
  const editing = topics.data?.find(topic => topic.id === topicId);
  const otherTopics = topics.data?.filter(topic => topic.id !== topicId) ?? [];
  const pendingRemovals = removals.filter(id => otherTopics.some(topic => topic.id === id));
  const saved = editing?.text ?? '';
  const value = draft ?? saved;
  const trimmed = value.trim().replace(/\s+/g, ' ');
  // Saving the same text again restarts a backfill that gave up.
  const retry = editing?.status === 'failed' && trimmed === saved;
  const atLimit = !editing && (topics.data?.length ?? 0) - pendingRemovals.length >= TOPIC_LIMIT;
  const topicSavable = trimmed.length >= 3 && (trimmed !== saved || retry) && !atLimit;
  // Set while a saved pop-up waits for fresh follows before opening afterSavePath; it stays disabled meanwhile.
  const [finishing, setFinishing] = useState(false);
  // Closing the pop-up unmounts the form, which cancels a pending navigation.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const saving = saveTopic.isPending || removeTopics.isPending || saveFollows.isPending || finishing;
  const isFollowed = (kind: FollowKind, id: string) =>
    follows.data?.some(follow => follow.kind === kind && String(follow.entity_id) === id) ?? false;
  const isSelected = (kind: FollowKind, id: string) =>
    selection.find(pick => pick.kind === kind && pick.id === id)?.follow ?? isFollowed(kind, id);
  const changes = selection.filter(pick => pick.follow !== isFollowed(pick.kind, pick.id));
  const submittable = !saving && (topicSavable || changes.length > 0 || pendingRemovals.length > 0);
  const toggle = (kind: FollowKind, id: string, name: string) => setSelection(current => [
    ...current.filter(pick => pick.kind !== kind || pick.id !== id),
    { kind, id, name, follow: !isSelected(kind, id) },
  ]);
  const submit = () => {
    if (!submittable) return;
    if (!user) {
      if (topicSavable) stashPendingTopic(trimmed);
      if (changes.length) stashPendingFollows(changes);
      window.location.href = hfLoginUrl(afterSavePath ?? `${location.pathname}${location.search}`);
      return;
    }
    // Save the follows, removals, and the topic independently, so one failing still saves the others.
    // Removals run before the topic save, so freeing a slot lets a new topic in at the limit.
    const removed = pendingRemovals.length ? removeTopics.mutateAsync(pendingRemovals) : Promise.resolve();
    const saves = [
      ...(changes.length ? [saveFollows.mutateAsync(changes)] : []),
      removed,
      ...(topicSavable ? [removed.catch(() => undefined).then(() => saveTopic.mutateAsync({ id: editing?.id, text: trimmed }))] : []),
    ];
    void Promise.allSettled(saves).then(async results => {
      if (!results.every(result => result.status === 'fulfilled')) return;
      if (afterSavePath) {
        // Let the destination see the saved follows and topics, or it would greet an "empty" account
        // with the intro and reopen this pop-up.
        setFinishing(true);
        await Promise.all([
          client.refetchQueries({ queryKey: researchQueryKeys.follows(user.hf_subject) }),
          client.refetchQueries({ queryKey: researchQueryKeys.topics(user.hf_subject) }),
        ]);
        if (!mounted.current) return;
        onDone();
        navigate(afterSavePath);
        return;
      }
      onDone();
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
      {topics.data?.length || follows.data?.length ? 'Edit your research feed' : 'Build your research feed'}
    </DialogTitle>
    <div className="topic-dialog-group">
      <h3><label htmlFor="topic-dialog-input">
        {editing ? 'Edit this topic' : topics.data?.length ? 'Add a topic in your own words' : 'Describe a topic in your own words'}
      </label></h3>
      <p className="topic-dialog-hint">
        {atLimit ? `You follow ${TOPIC_LIMIT} topics, the most allowed. Remove one below to add another.`
          : 'A model reads every new paper and adds the ones that match to your Following feed. New topics are public and show your Hugging Face username; make one private in Settings.'}
      </p>
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
    {otherTopics.length > 0 && <div className="topic-dialog-group">
      <h3>{editing ? 'Your other topics' : 'Your topics'}</h3>
      <div className="topic-dialog-chips">
        {otherTopics.map(topic => {
          const on = !removals.includes(topic.id);
          return <button key={topic.id} type="button" className="topic-dialog-chip" aria-pressed={on} disabled={saving}
            title={topic.text}
            onClick={() => setRemovals(current => on ? [...current, topic.id] : current.filter(id => id !== topic.id))}>
            {on ? <Check aria-hidden="true" /> : <Plus aria-hidden="true" />}
            {topicTitle(topic)}
          </button>;
        })}
      </div>
    </div>}
    {chips('Trending tasks', 'task', tasks.data?.results ?? [], { to: '/tasks', label: 'Browse tasks' })}
    {chips('Trending methods', 'method', methods.data?.results ?? [], { to: '/methods', label: 'Browse methods' })}
    {chips('Benchmarks', 'benchmark', [], { to: '/tasks', label: 'Browse benchmarks' })}
    {chips('Popular authors', 'author', suggested(suggestions.data?.authors))}
    {chips('Popular organizations', 'organization', suggested(suggestions.data?.organizations),
      { to: '/organizations', label: 'Browse organizations' })}
    {(saveTopic.error || removeTopics.error || saveFollows.error) && <p className="settings-token-error" role="alert">
      Could not save your feed. Please try again.
    </p>}
    <div className="topic-dialog-actions">
      {editing && <button type="button" className="research-follow-action topic-dialog-remove" disabled={saving}
        onClick={() => removeTopics.mutate([editing.id], { onSuccess: onDone })}>Remove topic</button>}
      <button type="button" className="research-follow-action" disabled={saving} onClick={onDone}>Cancel</button>
      <button type="submit" className="research-topic-save" disabled={!submittable}>
        {changes.some(change => change.follow === false) || pendingRemovals.length ? 'Save'
          : changes.length ? 'Follow' : retry ? 'Retry' : editing ? 'Update topic' : 'Follow'}
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

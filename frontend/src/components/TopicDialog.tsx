import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, ArrowUpRight, Check, Pencil, Plus, Trash2, Undo2 } from 'lucide-react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import TopicCard from '@/components/TopicCard';
import SortableList from '@/components/SortableList';
import { hfLoginUrl } from '@/lib/apiUrl';
import { saveTopicDialog, type TopicDialogSnapshot } from '@/lib/topicDialogSnapshot';
import {
  TOPIC_LIMIT, TOPIC_MAX_LENGTH, type FollowKind, type FollowSuggestion, type ResearchTopic,
} from '@/lib/api/research';
import { useAuth } from '@/lib/authContext';
import { useDebounce } from '@/hooks/useDebounce';
import { displayTaskName } from '@/lib/transform';
import { catalogQueries, researchQueries } from '@/lib/api/queries';
import {
  isConflict, stashPendingFollows, stashPendingTopic, stashPendingTopicFollows, topicTitle, useFollowTopic,
  useRemoveTopics, useReorderTopics, useResearchFollows, useResearchTopics, useSaveFollows, useSaveTopic,
  useSetTopicPublic, type FollowPick,
} from '@/lib/researchTopic';

// Suggestions fetched per group; each group shows as many as fit in two rows, after everything already followed,
// and links to its full listing for more.
const SUGGESTIONS_PER_GROUP = 16;
// Popular topics offered as cards after hiding the account's own and followed ones; two rows of the dialog's grid.
const POPULAR_TOPICS = 6;

/** Edits the Following feed in a pop-up, the one place to manage it. The Topics tab (the default) writes a new topic
 * or rewords one, reorders, unfollows, or makes your topics private, and offers popular topics as cards; the second
 * tab follows trending tasks and methods, benchmarks, popular authors, and organizations. Every chip and card links
 * to its page; following a link saves the pop-up as it is, and Back reopens it there with its unsaved picks
 * (`restore`).
 * Nothing is saved until Save. Guests sign in on submit, and /following saves what they picked when they return.
 * Opened elsewhere, `afterSavePath` (/following) is where a save leads and where guests return after signing in. */
export default function TopicDialog({ open, topicId = null, afterSavePath, restore, onOpenChange }: {
  open: boolean;
  topicId?: number | null;
  afterSavePath?: string;
  restore?: TopicDialogSnapshot | null;
  onOpenChange: (open: boolean) => void;
}) {
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="topic-dialog" aria-describedby={undefined}>
      <TopicDialogForm key={topicId ?? 'new'} topicId={topicId} afterSavePath={afterSavePath} restore={restore}
        onDone={() => onOpenChange(false)} />
    </DialogContent>
  </Dialog>;
}

/** Opens a chip's page, beside (never inside) the chip's toggle. */
function PageLink({ to, name }: { to: string; name: string }) {
  return <Link className="topic-dialog-chip-open" to={to} aria-label={`Open the ${name} page`} title="Open its page">
    <ArrowUpRight aria-hidden="true" />
  </Link>;
}

function TopicDialogForm({ topicId, afterSavePath, restore, onDone }: {
  topicId: number | null;
  afterSavePath?: string;
  restore?: TopicDialogSnapshot | null;
  onDone: () => void;
}) {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const topics = useResearchTopics();
  const follows = useResearchFollows();
  const tasks = useQuery(catalogQueries.trendingTasks({ limit: SUGGESTIONS_PER_GROUP, level: 0 }));
  const methods = useQuery(catalogQueries.trendingMethods({ limit: SUGGESTIONS_PER_GROUP }));
  // Popular authors, the directory's top organizations, and the benchmarks most reported on lately.
  const suggestions = useQuery(researchQueries.followSuggestions());
  const featured = useQuery(researchQueries.featuredTopics());
  const suggested = (items: FollowSuggestion[] = []) =>
    items.map(item => ({ id: String(item.entity_id), name: item.name, image: item.image_url, url: item.url }));
  // The topic loaded into the text box: one being reworded, or null for a new one.
  const [editId, setEditId] = useState(restore ? restore.editId : topicId);
  const [draft, setDraft] = useState<string | null>(restore?.draft ?? null);
  // The follow state chosen per chip; submit sends only those that differ from the current follows,
  // so chips stay right when a partial save refreshes the follows.
  const [selection, setSelection] = useState<FollowPick[]>(restore?.selection ?? []);
  // Followed topics show as chips; unselecting one removes it on submit.
  const [removals, setRemovals] = useState<number[]>(restore?.removals ?? []);
  // Popular topics picked to follow, a new order for your topics, and public/private switches, all saved on submit.
  const [topicFollows, setTopicFollows] = useState<number[]>(restore?.topicFollows ?? []);
  const [order, setOrder] = useState<ResearchTopic[] | null>(restore?.order ?? null);
  const [privacy, setPrivacy] = useState<Record<number, boolean>>(restore?.privacy ?? {});
  // Picks on either tab survive switching: both tabs' state lives here.
  const [tab, setTab] = useState(restore?.tab ?? 'topics');
  const form = useRef<HTMLFormElement>(null);
  // The scroll position to return to, applied once the restored pop-up is tall enough to reach it.
  const pendingScroll = useRef(restore?.scrollTop ?? 0);
  useLayoutEffect(() => {
    const scroller = form.current?.closest<HTMLElement>('.topic-dialog');
    if (!pendingScroll.current || !scroller) return;
    if (scroller.scrollHeight - scroller.clientHeight < pendingScroll.current) return;
    scroller.scrollTop = pendingScroll.current;
    pendingScroll.current = 0;
  });
  // A plain click on a link to another page of the site keeps the pop-up for Back.
  const keepForBack = (event: MouseEvent) => {
    const link = (event.target as Element).closest('a');
    if (!link || link.target === '_blank' || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey
      || event.altKey || new URL(link.href, window.location.href).origin !== window.location.origin) return;
    saveTopicDialog({
      topicId, editId, draft, selection, removals, topicFollows, order, privacy, tab,
      scrollTop: form.current?.closest<HTMLElement>('.topic-dialog')?.scrollTop ?? 0,
    });
  };
  const saveTopic = useSaveTopic();
  const removeTopics = useRemoveTopics();
  const saveFollows = useSaveFollows();
  const followTopic = useFollowTopic();
  const reorderTopics = useReorderTopics();
  const setTopicPublic = useSetTopicPublic();
  const ownTopics = topics.data ?? [];
  const editing = ownTopics.find(topic => topic.id === editId);
  // A topic named like a catalog task, method or benchmark would duplicate following it.
  const lookup = useDebounce(trimmedDraft(draft ?? editing?.text ?? '').toLowerCase());
  const lookupMatches = useQuery({ ...researchQueries.topicMatches(lookup), enabled: lookup.length >= 3 });
  // A stale order (a topic added or removed since) falls back to the saved one.
  const sameTopics = order?.length === ownTopics.length && order.every(topic => ownTopics.some(own => own.id === topic.id));
  const orderedTopics = order && sameTopics ? order : ownTopics;
  const reordered = orderedTopics.some((topic, index) => topic.id !== ownTopics[index]?.id);
  const pendingRemovals = removals.filter(id => ownTopics.some(topic => topic.id === id));
  const privacyChanges = Object.entries(privacy)
    .map(([id, isPublic]) => ({ id: Number(id), isPublic }))
    .filter(({ id, isPublic }) => !pendingRemovals.includes(id)
      && ownTopics.some(topic => topic.id === id && topic.is_creator && topic.is_public !== isPublic));
  const popularTopics = (featured.data ?? [])
    .filter(topic => !ownTopics.some(own => own.id === topic.id))
    .slice(0, POPULAR_TOPICS);
  const pendingTopicFollows = topicFollows.filter(id => popularTopics.some(topic => topic.id === id));
  const saved = editing?.text ?? '';
  const value = draft ?? saved;
  const trimmed = trimmedDraft(value);
  // Only matches for the text in the box count, not for what it said a moment ago.
  const lookupCurrent = lookup === trimmed.toLowerCase() && !lookupMatches.isFetching;
  const duplicates = lookupCurrent ? lookupMatches.data ?? [] : [];
  // The server's reason for refusing a topic, shown only while the box still holds that text.
  const refusal = isConflict(saveTopic.error) && saveTopic.variables?.text === trimmed ? saveTopic.error : null;
  // Saving the same text again restarts a backfill that gave up.
  const retry = editing?.status === 'failed' && trimmed === saved;
  const topicCount = ownTopics.length - pendingRemovals.length + pendingTopicFollows.length;
  const atLimit = topicCount >= TOPIC_LIMIT;
  // A reworded topic that is also unticked is only removed.
  // A text saved before its catalog check returns is refused by the server, which explains why.
  const topicSavable = trimmed.length >= 3 && (trimmed !== saved || retry) && !duplicates.length
    && (editing ? !pendingRemovals.includes(editing.id) : !atLimit);
  // Set while a saved pop-up waits for fresh follows before opening afterSavePath; it stays disabled meanwhile.
  const [finishing, setFinishing] = useState(false);
  // Closing the pop-up unmounts the form, which cancels a pending navigation.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const saving = saveTopic.isPending || removeTopics.isPending || saveFollows.isPending || followTopic.isPending
    || reorderTopics.isPending || setTopicPublic.isPending || finishing;
  const isFollowed = (kind: FollowKind, id: string) =>
    follows.data?.some(follow => follow.kind === kind && String(follow.entity_id) === id) ?? false;
  const isSelected = (kind: FollowKind, id: string) =>
    selection.find(pick => pick.kind === kind && pick.id === id)?.follow ?? isFollowed(kind, id);
  const changes = selection.filter(pick => pick.follow !== isFollowed(pick.kind, pick.id));
  const topicChanges = pendingRemovals.length + pendingTopicFollows.length + privacyChanges.length + (reordered ? 1 : 0);
  const submittable = !saving && (topicSavable || changes.length > 0 || topicChanges > 0);
  const toggle = (kind: FollowKind, id: string, name: string) => setSelection(current => [
    ...current.filter(pick => pick.kind !== kind || pick.id !== id),
    { kind, id, name, follow: !isSelected(kind, id) },
  ]);
  const startEditing = (id: number | null) => {
    setEditId(id);
    setDraft(null);
  };
  const submit = () => {
    if (!submittable) return;
    if (!user) {
      if (topicSavable) stashPendingTopic(trimmed);
      if (changes.length) stashPendingFollows(changes);
      if (pendingTopicFollows.length) stashPendingTopicFollows(pendingTopicFollows);
      window.location.href = hfLoginUrl(afterSavePath ?? `${location.pathname}${location.search}`);
      return;
    }
    // Save each part independently, so one failing still saves the others. Removals run first, so freeing a slot
    // lets a new topic in at the limit, then the new order (which must list exactly the remaining topics),
    // then additions, which append after it.
    const removed = pendingRemovals.length ? removeTopics.mutateAsync(pendingRemovals) : Promise.resolve();
    const kept = orderedTopics.filter(topic => !pendingRemovals.includes(topic.id));
    const sorted = removed.catch(() => undefined)
      .then(() => reordered ? reorderTopics.mutateAsync(kept) : undefined);
    const afterSort = sorted.catch(() => undefined);
    const saves = [
      ...(changes.length ? [saveFollows.mutateAsync(changes)] : []),
      removed,
      sorted,
      ...privacyChanges.map(change => setTopicPublic.mutateAsync(change)),
      ...(topicSavable ? [afterSort.then(() => saveTopic.mutateAsync({ id: editing?.id, text: trimmed }))] : []),
      ...pendingTopicFollows.map(id => afterSort.then(() => followTopic.mutateAsync(id))),
    ];
    void Promise.allSettled(saves).then(async results => {
      if (!results.every(result => result.status === 'fulfilled')) return;
      if (afterSavePath) {
        // Let the destination see the saved follows and topics, or it would greet an "empty" account
        // with the intro and reopen this pop-up.
        setFinishing(true);
        await Promise.all([
          client.refetchQueries({ queryKey: researchQueries.follows(user.hf_subject).queryKey }),
          client.refetchQueries({ queryKey: researchQueries.topics(user.hf_subject).queryKey }),
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
    suggestions: { id: string; name: string; slug?: string | null; image?: string | null; url?: string }[],
    browse?: { to: string; label: string },
  ) => {
    const followed = (follows.data ?? []).filter(follow => follow.kind === kind).map(follow => ({
      id: String(follow.entity_id), name: follow.name, slug: follow.url.split('/').pop(), image: follow.image_url,
      url: follow.url,
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
          const url = item.url ?? `/${kind === 'task' ? 'tasks' : 'methods'}/${item.slug ?? item.id}`;
          return <span key={item.id} className="topic-dialog-chip-wrap" data-suggested={'suggested' in item || undefined}>
            <button type="button" className="topic-dialog-chip" aria-pressed={on} disabled={saving}
              onClick={() => toggle(kind, item.id, name)}>
              {on ? <Check aria-hidden="true" /> : <Plus aria-hidden="true" />}
              {(kind === 'author' || kind === 'organization') && <ChipImage kind={kind} name={name} src={item.image} />}
              {name}
            </button>
            <PageLink to={url} name={name} />
          </span>;
        })}
        {browse && <Link to={browse.to} className="topic-dialog-browse">{browse.label}<ArrowRight aria-hidden="true" /></Link>}
      </TwoRowChips>
    </div>;
  };
  const editingPublic = editing ? privacy[editing.id] ?? editing.is_public : true;
  return <form ref={form} className="topic-dialog-form" onClickCapture={keepForBack} onSubmit={event => {
    event.preventDefault();
    submit();
  }}>
    <DialogTitle className="topic-dialog-title">
      {topics.data?.length || follows.data?.length ? 'Edit your research feed' : 'Build your research feed'}
    </DialogTitle>
    <Tabs value={tab} onValueChange={setTab} className="topic-dialog-tabs">
      <TabsList className="topic-dialog-tab-list">
        <TabsTrigger value="topics" className="topic-dialog-tab">
          Topics<TabCount count={pendingTopicFollows.length + pendingRemovals.length} />
        </TabsTrigger>
        <TabsTrigger value="catalog" className="topic-dialog-tab">
          Tasks, methods &amp; more<TabCount count={changes.length} />
        </TabsTrigger>
      </TabsList>
      <TabsContent value="topics" className="topic-dialog-panel">
        <div className="topic-dialog-group">
          <h3><label htmlFor="topic-dialog-input">
            {editing ? `Reword “${topicTitle(editing)}”` : topics.data?.length ? 'Add a topic in your own words' : 'Describe a topic in your own words'}
          </label></h3>
          <p className="topic-dialog-hint">
            {!editing && atLimit ? `You follow ${TOPIC_LIMIT} topics, the most allowed. Remove one below to add another.`
              : <>
                A model reads every new paper and adds the ones that match to your <Link to="/following"
                  className="topic-dialog-feed-link" onClick={onDone}>Following feed</Link>. New topics are public and show your Hugging Face username; make one private from
                its ✎ button below, or remove one with its trash button.
              </>}
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
          {duplicates.length > 0 && <div className="topic-dialog-duplicate" role="status">
            <p>
              Papers with Code already has {duplicates.length > 1 ? 'pages' : `a ${duplicates[0].kind} page`} for
              “{trimmed}”. Follow {duplicates.length > 1 ? 'one' : 'it'} instead of adding a topic:
            </p>
            <div className="topic-dialog-chips">
              {duplicates.map(match => {
                const id = String(match.entity_id);
                const on = isSelected(match.kind, id);
                return <span key={`${match.kind}:${id}`} className="topic-dialog-chip-wrap">
                  <button type="button" className="topic-dialog-chip" aria-pressed={on} disabled={saving}
                    onClick={() => toggle(match.kind, id, match.name)}>
                    {on ? <Check aria-hidden="true" /> : <Plus aria-hidden="true" />}
                    {match.name}
                  </button>
                  <PageLink to={match.url} name={match.name} />
                </span>;
              })}
            </div>
          </div>}
          {editing && <div className="topic-dialog-editing">
            {editing.is_creator && <label className="topic-dialog-privacy">
              <Switch checked={editingPublic} disabled={saving} aria-label="Public topic"
                onCheckedChange={checked => setPrivacy(current => ({ ...current, [editing.id]: checked }))} />
              {editingPublic ? 'Public: anyone can find and follow it' : 'Private: only you see it'}
            </label>}
            <button type="button" className="link-button" disabled={saving} onClick={() => startEditing(null)}>
              Add a new topic instead
            </button>
          </div>}
        </div>
        {ownTopics.length > 0 && <div className="topic-dialog-group">
          <h3>Your topics</h3>
          <SortableList
            className="home-topics-list topic-dialog-topic-cards"
            grid
            items={orderedTopics}
            itemKey={topic => topic.id}
            itemLabel={topic => topicTitle(topic)}
            disabled={saving}
            onReorder={setOrder}
            renderItem={(topic, handle) => {
              const on = !removals.includes(topic.id);
              const title = topicTitle(topic);
              const toggleRemoval = () => setRemovals(current => on ? [...current, topic.id] : current.filter(id => id !== topic.id));
              return <TopicCard as="div" topic={topic} showCreator
                className={`topic-dialog-own-topic ${topic.id === editId ? 'is-editing' : ''} ${on ? '' : 'is-removed'}`}
                action={<div className="topic-dialog-card-actions">
                  <button type="button" className={`home-topic-follow ${on ? 'is-following' : ''}`} aria-pressed={on}
                    aria-label={title} title={on ? 'Remove from your feed on Save' : 'Keep this topic'} disabled={saving}
                    onClick={toggleRemoval}>
                    {on ? <Check aria-hidden="true" /> : <Plus aria-hidden="true" />}{on ? 'Following' : 'Follow'}
                  </button>
                  <button type="button" className="topic-dialog-chip-open" disabled={saving || topic.id === editId}
                    aria-label={`Reword ${title}`} title="Reword this topic" onClick={() => startEditing(topic.id)}>
                    <Pencil aria-hidden="true" />
                  </button>
                  <button type="button" className="topic-dialog-chip-open topic-dialog-chip-remove" disabled={saving}
                    aria-label={on ? `Remove ${title}` : `Keep ${title}`}
                    title={on ? 'Remove from your feed on Save' : 'Keep this topic'} onClick={toggleRemoval}>
                    {on ? <Trash2 aria-hidden="true" /> : <Undo2 aria-hidden="true" />}
                  </button>
                  <span className="topic-dialog-card-handle">{handle}</span>
                </div>} />;
            }}
          />
        </div>}
        {popularTopics.length > 0 && <div className="topic-dialog-group">
          <h3>Popular topics</h3>
          <ul className="home-topics-list topic-dialog-topic-cards">
            {popularTopics.map(topic => {
              const on = topicFollows.includes(topic.id);
              return <TopicCard key={topic.id} topic={topic} showCreator action={
                <button type="button" className={`home-topic-follow ${on ? 'is-following' : ''}`} aria-pressed={on}
                  aria-label={`Follow ${topicTitle(topic)}`} disabled={saving || (!on && atLimit)}
                  onClick={() => setTopicFollows(current => on ? current.filter(id => id !== topic.id) : [...current, topic.id])}>
                  {on ? <Check aria-hidden="true" /> : <Plus aria-hidden="true" />}{on ? 'Following' : 'Follow'}
                </button>
              } />;
            })}
          </ul>
        </div>}
      </TabsContent>
      <TabsContent value="catalog" className="topic-dialog-panel">
        {chips('Trending tasks', 'task', tasks.data?.results ?? [], { to: '/tasks', label: 'Browse tasks' })}
        {chips('Trending methods', 'method', methods.data?.results ?? [], { to: '/methods', label: 'Browse methods' })}
        {chips('Popular benchmarks', 'benchmark', suggested(suggestions.data?.benchmarks),
          { to: '/tasks', label: 'Browse benchmarks' })}
        {chips('Popular authors', 'author', suggested(suggestions.data?.authors))}
        {chips('Popular organizations', 'organization', suggested(suggestions.data?.organizations),
          { to: '/organizations', label: 'Browse organizations' })}
      </TabsContent>
    </Tabs>
    {refusal && <p className="settings-token-error" role="alert">{refusal.message}.</p>}
    {((saveTopic.error && !isConflict(saveTopic.error)) || removeTopics.error || saveFollows.error || followTopic.error
      || reorderTopics.error || setTopicPublic.error) && <p className="settings-token-error" role="alert">
      Could not save your feed. Please try again.
    </p>}
    <div className="topic-dialog-actions">
      <button type="button" className="research-follow-action" disabled={saving} onClick={onDone}>Cancel</button>
      <button type="submit" className="research-topic-save" disabled={!submittable}>
        {changes.some(change => change.follow === false) || pendingRemovals.length || reordered || privacyChanges.length
          ? 'Save' : changes.length || pendingTopicFollows.length ? 'Follow' : retry ? 'Retry' : editing ? 'Update topic' : 'Follow'}
      </button>
    </div>
  </form>;
}

/** How many unsaved picks a tab holds, so a switch never hides them. */
function TabCount({ count }: { count: number }) {
  return count > 0 ? <span className="topic-dialog-tab-count" aria-label={`${count} unsaved`}>{count}</span> : null;
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

const trimmedDraft = (text: string) => text.trim().replace(/\s+/g, ' ');

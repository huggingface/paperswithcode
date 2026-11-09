import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Building2, Pencil, User } from 'lucide-react';
import type { FollowKind, ResearchFollow, ResearchTopic } from '@/lib/api/research';
import { chipColors, hueFromSlug } from '@/lib/colors';
import { topicTitle } from '@/lib/researchTopic';
import { taskIcon } from '@/lib/taskIcons';

/** Bubbles shown before the row collapses behind "+N more". */
export const VISIBLE_BUBBLES = 12;
const KIND_ORDER: FollowKind[] = ['organization', 'author', 'task', 'method', 'benchmark'];
const KIND_LABELS: Record<FollowKind, string> = {
  task: 'Task', method: 'Method', benchmark: 'Benchmark', author: 'Author', organization: 'Organization',
};

/** The selected bubbles: topic ids and follows as `<kind>:<entity_id>`. Nothing selected shows everything. */
export type FeedFilter = { topicIds: number[]; follows: string[] };

const NO_FILTER: FeedFilter = { topicIds: [], follows: [] };

const followKey = (follow: Pick<ResearchFollow, 'kind' | 'entity_id'>) => `${follow.kind}:${follow.entity_id}`;

/** Followed entities for the bubble row: grouped by kind, newest first within a kind. */
function orderFollows(follows: ResearchFollow[]): ResearchFollow[] {
  return [...follows].sort((a, b) =>
    KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind) || b.created_at.localeCompare(a.created_at));
}

function FollowMark({ follow }: { follow: ResearchFollow }) {
  if (follow.kind === 'task') {
    const slug = follow.url.split('/').pop() ?? '';
    const Icon = taskIcon(slug, follow.parent_slug ?? undefined);
    return <Icon size={14} strokeWidth={2} aria-hidden="true" style={{ color: chipColors(hueFromSlug(slug)).dot }} />;
  }
  if (follow.kind === 'author' || follow.kind === 'organization') {
    if (follow.image_url) return <img src={follow.image_url} alt="" width={18} height={18} loading="lazy" />;
    const Icon = follow.kind === 'author' ? User : Building2;
    return <Icon size={14} aria-hidden="true" />;
  }
  return null;
}

const toggle = <T,>(values: T[], value: T) =>
  values.includes(value) ? values.filter(v => v !== value) : [...values, value];

/**
 * The /following filter row: All, the account's topics and follows, and the Edit feed button.
 * Each bubble toggles on or off; the feed shows papers matching any selected bubble.
 */
export default function FollowBubbles({ topics, follows, active, hrefFor, onEdit, editLabel }: {
  topics: ResearchTopic[];
  follows: ResearchFollow[];
  active: FeedFilter;
  hrefFor: (filter: FeedFilter) => string;
  onEdit?: () => void;
  editLabel: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const bubbles = [
    ...topics.map(topic => ({
      key: `topic:${topic.id}`,
      filter: { ...active, topicIds: toggle(active.topicIds, topic.id) },
      name: topicTitle(topic),
      title: topic.text,
      mark: null as React.ReactNode,
      on: active.topicIds.includes(topic.id),
    })),
    ...orderFollows(follows).map(follow => ({
      key: followKey(follow),
      filter: { ...active, follows: toggle(active.follows, followKey(follow)) },
      name: follow.name,
      title: `${KIND_LABELS[follow.kind]} · ${follow.name}`,
      mark: <FollowMark follow={follow} />,
      on: active.follows.includes(followKey(follow)),
    })),
  ];
  const all = active.topicIds.length === 0 && active.follows.length === 0;
  // Keep selected bubbles visible even when they sit past the fold.
  const collapsed = !expanded && bubbles.length > VISIBLE_BUBBLES + 1;
  const shown = collapsed
    ? bubbles.filter((bubble, index) => index < VISIBLE_BUBBLES || bubble.on)
    : bubbles;
  const hidden = bubbles.length - shown.length;
  return <nav className="topic-bubbles follow-bubbles" aria-label="Filter your feed">
    {bubbles.length > 0 && <Link className={`topic-bubble ${all ? 'active' : ''}`} to={hrefFor(NO_FILTER)}
      aria-current={all ? 'true' : undefined}>
      <span className="topic-bubble-name">All</span>
    </Link>}
    {shown.map(bubble => <Link key={bubble.key} className={`topic-bubble ${bubble.on ? 'active' : ''}`}
      to={hrefFor(bubble.filter)} title={bubble.title} aria-current={bubble.on ? 'true' : undefined}>
      {bubble.mark}
      <span className="topic-bubble-name">{bubble.name}</span>
    </Link>)}
    {hidden > 0 && <button type="button" className="topic-bubble topic-bubble-more" onClick={() => setExpanded(true)}>
      <span className="topic-bubble-name">+{hidden} more</span>
    </button>}
    {onEdit && <button type="button" className="topic-bubble topic-bubble-add" onClick={onEdit}>
      <Pencil size={13} aria-hidden="true" />
      <span className="topic-bubble-name">{editLabel}</span>
    </button>}
  </nav>;
}

import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { assetUrl } from '@/lib/apiUrl';
import type { ResearchTopic, TopicBubble, TopicPerson } from '@/lib/api/research';
import { topicPath, topicTitle } from '@/lib/researchTopic';

/** A topic as a card: its title, followers' faces, this week's papers and the top one, then `action`.
 * `newTab` opens its links in a new tab, so a look from the feed editor keeps unsaved picks; `showCreator`
 * names who wrote the topic. `as="div"` fits it inside a list item someone else renders. */
export default function TopicCard({ topic, action, newTab = false, showCreator = false, kindLabel, as = 'li', className }: {
  topic: TopicBubble | ResearchTopic;
  action: ReactNode;
  newTab?: boolean;
  showCreator?: boolean;
  kindLabel?: string;
  as?: 'li' | 'div';
  className?: string;
}) {
  return <FollowCard
    title={topicTitle(topic)}
    href={topicPath(topic)}
    kindLabel={kindLabel}
    creator={showCreator ? topic.creator?.username : undefined}
    followers={topic.followers}
    avatars={topic.follower_avatars ?? []}
    weekPapers={topic.week_papers}
    paper={topic.top_paper}
    action={action}
    newTab={newTab}
    as={as}
    className={className}
  />;
}

/** Anything followable as a card: an optional kind label, its title, followers' faces, this week's papers
 * and the top one, then `action`. */
export function FollowCard({
  title, href, kindLabel, creator, followers, avatars, weekPapers, paper, action, newTab = false, as: Tag = 'li', className,
}: {
  title: string;
  href: string;
  kindLabel?: string;
  creator?: string;
  followers?: number | null;
  avatars: TopicPerson[];
  weekPapers?: number | null;
  paper?: { id: number; arxiv_id: string | null; title: string } | null;
  action: ReactNode;
  newTab?: boolean;
  as?: 'li' | 'div';
  className?: string;
}) {
  return <Tag className={['home-topic-card', className].filter(Boolean).join(' ')}>
    {kindLabel && <span className="home-topic-kind">{kindLabel}</span>}
    <CardLink to={href} newTab={newTab} className="home-topic-title">{title}</CardLink>
    {creator && <div className="home-topic-creator">by @{creator}</div>}
    {followers != null && <div className="home-topic-followers">
      {avatars.length > 0 && <span className="home-topic-avatars" aria-hidden="true">
        {avatars.map(person => <FollowerAvatar key={person.username} person={person} />)}
      </span>}
      {followers} {followers === 1 ? 'follower' : 'followers'}
    </div>}
    {!!weekPapers && <div className="home-topic-meta">
      {weekPapers} new {weekPapers === 1 ? 'paper' : 'papers'} this week
    </div>}
    {paper && <CardLink to={`/paper/${paper.arxiv_id || paper.id}`} newTab={newTab} className="home-topic-paper"
      title={paper.title}>
      {paper.title}
    </CardLink>}
    {action}
  </Tag>;
}

function CardLink({ to, newTab, className, title, children }: {
  to: string;
  newTab: boolean;
  className: string;
  title?: string;
  children: ReactNode;
}) {
  return newTab
    ? <a href={to} target="_blank" rel="noopener noreferrer" className={className} title={title}>{children}</a>
    : <Link to={to} className={className} title={title}>{children}</Link>;
}

/** A follower's face, or their initial when the image does not load. */
function FollowerAvatar({ person }: { person: TopicPerson }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return <span className="topic-avatar home-topic-avatar-initial">{person.username.charAt(0).toUpperCase()}</span>;
  }
  return <img
    className="topic-avatar"
    src={assetUrl(person.avatar_url) ?? undefined}
    alt=""
    width={20}
    height={20}
    loading="lazy"
    onError={() => setFailed(true)}
  />;
}

import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { assetUrl } from '@/lib/apiUrl';
import type { ResearchTopic, TopicBubble, TopicPerson } from '@/lib/api/research';
import { topicPath, topicTitle } from '@/lib/researchTopic';

/** A topic as a card: its title, followers' faces, this week's papers and the top one, then `action`.
 * `newTab` opens its links in a new tab, so a look from the feed editor keeps unsaved picks; `showCreator`
 * names who wrote the topic. `as="div"` fits it inside a list item someone else renders. */
export default function TopicCard({ topic, action, newTab = false, showCreator = false, as: Tag = 'li', className }: {
  topic: TopicBubble | ResearchTopic;
  action: ReactNode;
  newTab?: boolean;
  showCreator?: boolean;
  as?: 'li' | 'div';
  className?: string;
}) {
  const avatars = topic.follower_avatars ?? [];
  const paper = topic.top_paper;
  return <Tag className={['home-topic-card', className].filter(Boolean).join(' ')}>
    <CardLink to={topicPath(topic)} newTab={newTab} className="home-topic-title">{topicTitle(topic)}</CardLink>
    {showCreator && topic.creator && <div className="home-topic-creator">by @{topic.creator.username}</div>}
    {topic.followers != null && <div className="home-topic-followers">
      {avatars.length > 0 && <span className="home-topic-avatars" aria-hidden="true">
        {avatars.map(person => <FollowerAvatar key={person.username} person={person} />)}
      </span>}
      {topic.followers} {topic.followers === 1 ? 'follower' : 'followers'}
    </div>}
    {!!topic.week_papers && <div className="home-topic-meta">
      {topic.week_papers} new {topic.week_papers === 1 ? 'paper' : 'papers'} this week
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

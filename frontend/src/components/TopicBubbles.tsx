import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { researchApi } from '@/lib/api/research';
import { researchQueryKeys, TEN_MINUTES } from '@/lib/api/queryKeys';
import { topicPath, topicTitle } from '@/lib/researchTopic';

/** Popular public topics, each with its creator's Hugging Face avatar, and with `onAddTopic` a last bubble that
 * opens the topic pop-up; hidden while loading, and when there is nothing to show. */
export default function TopicBubbles({ onAddTopic }: { onAddTopic?: () => void }) {
  const bubbles = useQuery({
    queryKey: researchQueryKeys.featuredTopics,
    queryFn: researchApi.featuredTopics,
    staleTime: TEN_MINUTES,
  });
  if (bubbles.isPending || (!bubbles.data?.length && !onAddTopic)) return null;
  return <nav className="topic-bubbles" aria-label="Popular topics">
    {bubbles.data?.map(topic => <Link key={topic.id} className="topic-bubble" to={topicPath(topic)}
      title={`${topic.followers.toLocaleString()} ${topic.followers === 1 ? 'follower' : 'followers'}`}>
      {topic.creator && <img src={topic.creator.avatar_url} alt="" width={20} height={20} loading="lazy" />}
      <span className="topic-bubble-name">{topicTitle(topic)}</span>
      {topic.creator && <span className="topic-bubble-creator">@{topic.creator.username}</span>}
    </Link>)}
    {onAddTopic && <button type="button" className="topic-bubble topic-bubble-add" onClick={onAddTopic}>
      <Plus size={14} aria-hidden="true" />
      <span className="topic-bubble-name">Add topic</span>
    </button>}
  </nav>;
}

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { researchApi } from '@/lib/api/research';
import { researchQueryKeys, TEN_MINUTES } from '@/lib/api/queryKeys';
import { topicPath, topicTitle } from '@/lib/researchTopic';

/** Popular public topics, each with its creator's Hugging Face avatar; hidden when there are none. */
export default function TopicBubbles() {
  const bubbles = useQuery({
    queryKey: researchQueryKeys.featuredTopics,
    queryFn: researchApi.featuredTopics,
    staleTime: TEN_MINUTES,
  });
  if (!bubbles.data?.length) return null;
  return <nav className="topic-bubbles" aria-label="Popular topics">
    {bubbles.data.map(topic => <Link key={topic.id} className="topic-bubble" to={topicPath(topic)}
      title={`${topic.followers.toLocaleString()} ${topic.followers === 1 ? 'follower' : 'followers'}`}>
      {topic.creator && <img src={topic.creator.avatar_url} alt="" width={20} height={20} loading="lazy" />}
      <span className="topic-bubble-name">{topicTitle(topic)}</span>
      {topic.creator && <span className="topic-bubble-creator">@{topic.creator.username}</span>}
    </Link>)}
  </nav>;
}

import { useState } from 'react';
import type { TopicPerson } from '@/lib/api/research';
import { assetUrl } from '@/lib/apiUrl';

/** A follower's face from the API origin, or the username's initial when the image does not load. */
export default function FollowerAvatar({ person, size }: { person: TopicPerson; size: number }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return <span className="topic-avatar home-topic-avatar-initial" title={`@${person.username}`}
      style={{ width: size, height: size, fontSize: size * 0.45 }}>{person.username.charAt(0).toUpperCase()}</span>;
  }
  return <img className="topic-avatar" src={assetUrl(person.avatar_url) ?? undefined} alt="" title={`@${person.username}`}
    width={size} height={size} loading="lazy" onError={() => setFailed(true)} />;
}

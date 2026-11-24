import { useQuery } from '@tanstack/react-query';
import type { FollowKind } from '@/lib/api/research';
import { researchQueries } from '@/lib/api/queries';

/** Overlapping faces of the first followers who show their avatar, then "+N" and the follower count. */
export default function FollowerStack({ kind, entityId }: { kind: FollowKind; entityId: string | number }) {
  const { data } = useQuery(researchQueries.entityFollowers(kind, entityId));
  if (!data?.followers) return null;
  const rest = data.followers - data.follower_avatars.length;
  return <div className="follower-stack">
    {data.follower_avatars.length > 0 && <ul className="follower-stack-faces" aria-label="Followers">
      {data.follower_avatars.map(p => <li key={p.username}>
        <a href={`https://huggingface.co/${p.username}`} target="_blank" rel="noreferrer" aria-label={`@${p.username}`}>
          <img className="topic-avatar" src={p.avatar_url} alt="" title={`@${p.username}`} width={28} height={28} loading="lazy" />
        </a>
      </li>)}
      {rest > 0 && <li className="follower-stack-more" aria-label={`${rest.toLocaleString()} more`}>+{rest.toLocaleString()}</li>}
    </ul>}
    <span className="follower-stack-count">
      <strong>{data.followers.toLocaleString()}</strong> {data.followers === 1 ? 'follower' : 'followers'}
    </span>
  </div>;
}

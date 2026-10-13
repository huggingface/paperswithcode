import { useEffect } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { researchApi } from '@/lib/api/research';
import { useAuth } from '@/lib/authContext';
import HfSignInButton from '@/components/HfSignInButton';
import ResearchFeedTabs from '@/components/ResearchFeedTabs';
import { Button } from '@/components/ui/button';

export default function FollowingView() {
  const { user, isLoading } = useAuth();
  const feed = useInfiniteQuery({
    queryKey: ['research-feed', user?.hf_subject], queryFn: ({ pageParam }) => researchApi.following(pageParam),
    initialPageParam: 0, getNextPageParam: (last, pages) => last.length === 40 ? pages.length * 40 : undefined,
    enabled: !!user,
  });
  useEffect(() => { document.title = 'Following · Papers With Code'; }, []);
  const entries = feed.data?.pages.flat() ?? [];
  return <div className="page">
    <h1 className="feed-title">Following</h1>
    <p className="feed-subtitle mb-6">Research from the past 30 days, matched to your private interests. <Link to="/settings">Manage follows</Link></p>
    <ResearchFeedTabs />
    {isLoading || (user && feed.isLoading) ? <p>Loading your research…</p> : !user ?
      <HfSignInButton returnTo="/following" label="Sign in to see your follows" /> : <>
        {feed.error && <p role="alert">Could not load your feed. <button onClick={() => void feed.refetch()}>Try again</button></p>}
        {!feed.error && entries.length === 0 && <p>No recent matches yet. Follow interests from <Link to="/tasks">tasks</Link>, <Link to="/methods">methods</Link>, benchmark, author, or organization pages.</p>}
        <ol className="paper-list">{entries.map(e => <li key={e.paper_key} className="py-6 border-b">
          <h2 className="text-xl"><Link to={e.url}>{e.title}</Link></h2>
          <p className="text-sm my-2">{e.published} · {e.reasons.join(' · ')}</p>
          <p>{e.summary}</p>
          {e.scores.map((s, index) => <p key={index} className="text-sm mt-2"><strong>{s.benchmark}</strong>{s.model ? ` · ${s.model}` : ''}: {Object.entries(s.metrics).map(([k, v]) => `${k}: ${String(v)}`).join(', ')}</p>)}
        </li>)}</ol>
        {feed.hasNextPage && <Button disabled={feed.isFetchingNextPage} onClick={() => void feed.fetchNextPage()}>Load more</Button>}
      </>}
  </div>;
}

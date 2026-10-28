import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { researchApi } from '@/lib/api/research';
import { catalogApi } from '@/lib/api/catalog';
import { papersApi } from '@/lib/api/papers';
import FollowingView from './FollowingView';
import FeedView from './FeedView';

const auth = vi.hoisted(() => ({ user: { hf_subject: 'alice', username: 'alice' } as { hf_subject: string; username: string } | null, isLoading: false }));
vi.mock('@/lib/authContext', () => ({ useAuth: () => auth, useOptionalAuth: () => auth }));
vi.mock('@/hooks/useIntersectionObserver', () => ({ useIntersectionObserver: () => ({ targetRef: () => {}, isIntersecting: false }) }));
const paper = { id: '1', arxiv_id: '2610.12345', title: 'A paper', abstract: 'Full abstract.',
  published: '2026-10-10', authors: ['An Author'], version: '1', is_latest_version: true,
  citation_count: 12, url_abs: null, url_pdf: null, thumbnail_url: '/api/thumbnails/example.png' };
function renderFeed(path = '/following') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/" element={<FeedView />} /><Route path="/following" element={<FollowingView />} />
  </Routes></MemoryRouter></QueryClientProvider>);
}
beforeEach(() => {
  auth.user = { hf_subject: 'alice', username: 'alice' };
  vi.stubEnv('VITE_CHAT_ENABLED', '0');
  vi.spyOn(catalogApi, 'topTasks').mockResolvedValue([]);
  vi.spyOn(catalogApi, 'trendingTasks').mockResolvedValue({ results: [], recent_days: 7, baseline_days: 30 });
  vi.spyOn(papersApi, 'list').mockResolvedValue({ count: 0, results: [], next_page: null, previous_page: null });
  vi.spyOn(researchApi, 'follows').mockResolvedValue([
    { kind: 'task', entity_id: 1, name: 'Task', url: '/tasks/task', created_at: '' },
  ]);
  vi.spyOn(researchApi, 'following').mockResolvedValue([{ paper, paper_key: 'arxiv:2610.12345',
    title: paper.title, url: '/paper/2610.12345', summary: 'Short summary.', published: paper.published,
    reasons: ['Task'], scores: [] }]);
  vi.spyOn(researchApi, 'topic').mockResolvedValue(null);
});
const topic = { text: 'real-time video generation', set_at: '2026-10-28T10:00:00Z', status: 'done' as const,
  judged: 10, total: 10, suggestions: [] };
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); });
it('renders following in the existing tab row with standard paper cards and thumbnails', async () => {
  const { container } = renderFeed();
  await screen.findByText('A paper');
  expect(container.querySelector('.paper-card .paper-thumb-wrap img')).toHaveAttribute('src', expect.stringContaining('/api/thumbnails/example.png'));
  expect(container.querySelector('.paper-authors')).toHaveTextContent('An Author');
  expect(container.querySelector('.paper-follow-reason')).toHaveTextContent('Because you follow Task');
  expect(screen.getByText('Full abstract.')).toBeInTheDocument();
  const tab = screen.getByRole('button', { name: 'following' });
  expect(tab).toHaveClass('active');
  expect(tab.parentElement?.textContent).toBe('trendingnewestmost citedfollowing');
  expect(screen.queryByText('Discover')).not.toBeInTheDocument();
  expect(papersApi.list).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'newest' }));
  expect(await screen.findByText('No papers in this window.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'newest' })).toHaveClass('active');
});
it('opens Following from the public feed', async () => {
  renderFeed('/');
  await screen.findByText('No papers in this window.');
  expect(researchApi.following).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'following' }));
  await screen.findByText('A paper');
  expect(screen.getByRole('button', { name: 'following' })).toHaveClass('active');
});
it('names every distinct follow that matched, collapsing subtasks and long lists', async () => {
  vi.mocked(researchApi.following).mockResolvedValue([{ paper, paper_key: 'arxiv:2610.12345',
    title: paper.title, url: '/paper/2610.12345', summary: '', published: paper.published,
    reasons: ['Agents (subtask)', 'Agents', 'Reasoning', 'Jane Doe', 'Hugging Face'], scores: [] }]);
  const { container } = renderFeed();
  await screen.findByText('A paper');
  expect(container.querySelector('.paper-follow-reason')).toHaveTextContent('Because you follow Agents, Reasoning and 2 more');
});
it('explains how to start following to signed-out visitors without fetching private papers', async () => {
  auth.user = null;
  renderFeed();
  expect(await screen.findByRole('heading', { name: 'Build your personal research feed' })).toBeInTheDocument();
  expect(screen.getByText(/Sign in with your Hugging Face account/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Sign in with Hugging Face' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Browse tasks/ })).toHaveAttribute('href', '/tasks');
  expect(researchApi.following).not.toHaveBeenCalled();
});

it('explains how to follow when a signed-in account follows nothing yet', async () => {
  vi.mocked(researchApi.follows).mockResolvedValue([]);
  vi.mocked(researchApi.following).mockResolvedValue([]);
  vi.mocked(catalogApi.topTasks).mockResolvedValue([
    { id: '1', name: 'Object Detection', slug: 'object-detection', paper_count: 10 } as never,
  ]);
  renderFeed();
  expect(await screen.findByRole('heading', { name: 'Build your personal research feed' })).toBeInTheDocument();
  expect(screen.queryByText(/Sign in with your Hugging Face account/)).not.toBeInTheDocument();
  expect(await screen.findByRole('link', { name: 'Object Detection' })).toHaveAttribute('href', '/tasks/object-detection');
  expect(screen.queryByText(/match these filters/)).not.toBeInTheDocument();
});

it('keeps the filter hint when follows exist but nothing matches', async () => {
  vi.mocked(researchApi.following).mockResolvedValue([]);
  renderFeed();
  expect(await screen.findByText(/No papers from your topic or follows match these filters/)).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Build your personal research feed' })).not.toBeInTheDocument();
});

it('offers a retry instead of claiming the feed is empty when loading fails', async () => {
  vi.mocked(researchApi.following).mockRejectedValueOnce(new Error('Unavailable'));
  renderFeed();
  expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load papers.');
  expect(screen.queryByText(/No papers from your follows/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  await screen.findByText('A paper');
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('offers the home feed filters on Following and sends them to the feed', async () => {
  renderFeed();
  await screen.findByText('A paper');
  // Following defaults to its 30-day window.
  expect(screen.getByRole('button', { name: 'Last Month' })).toHaveClass('active');
  const [, defaults] = vi.mocked(researchApi.following).mock.calls[0];
  expect(defaults).toMatchObject({ hasCode: false, hasHfArtifacts: false });
  expect(defaults?.startDate).toBeDefined();
  fireEvent.click(screen.getByRole('button', { name: /Has code/ }));
  fireEvent.click(screen.getByRole('button', { name: 'All Time' }));
  await vi.waitFor(() => expect(researchApi.following).toHaveBeenLastCalledWith(0, {
    startDate: undefined, endDate: undefined, hasCode: true, hasHfArtifacts: false, topicOnly: false,
  }));
  expect(screen.getByRole('button', { name: /Has code/ })).toHaveAttribute('aria-pressed', 'true');
});

it('keeps filters when switching from the public feed to Following', async () => {
  renderFeed('/?has_hf_artifacts=true&start_date=2026-09-01&end_date=2026-09-30&order_by=date_published');
  await screen.findByText('No papers in this window.');
  fireEvent.click(screen.getByRole('button', { name: 'following' }));
  await screen.findByText('A paper');
  expect(researchApi.following).toHaveBeenLastCalledWith(0, {
    startDate: '2026-09-01', endDate: '2026-09-30', hasCode: false, hasHfArtifacts: true, topicOnly: false,
  });
});

it('lists followed entities with kind badges in the sidebar', async () => {
  vi.mocked(researchApi.follows).mockResolvedValue([
    { kind: 'organization', entity_id: 7, name: 'Liquid AI', url: '/organizations/liquid-ai', created_at: '' },
    { kind: 'task', entity_id: 1, name: 'Coding Agents', url: '/tasks/coding-agents', created_at: '' },
  ]);
  const { container } = renderFeed();
  const links = await screen.findAllByRole('link', { name: /Coding Agents|Liquid AI/ });
  expect(links.map(link => link.textContent)).toEqual(['TaskCoding Agents', 'OrgLiquid AI']);
  expect(links[1]).toHaveAttribute('href', '/organizations/liquid-ai');
  expect(container.querySelector('.sidebar-section-top-domains')).toBeNull();
});

it('keeps domain lists out of the Following sidebar while follows load', () => {
  vi.mocked(researchApi.follows).mockReturnValue(new Promise(() => {}));
  const { container } = renderFeed();
  expect(screen.getByText('You follow')).toBeInTheDocument();
  expect(container.querySelector('.sidebar-section-top-domains')).toBeNull();
});

it('lists the topic first in the sidebar as a filter with an edit link, and links Settings below', async () => {
  vi.mocked(researchApi.topic).mockResolvedValue(topic);
  renderFeed();
  const row = await screen.findByRole('link', { name: /^Topic real-time video generation$/ });
  expect(row).toHaveAttribute('href', '/following?only=topic');
  expect(screen.getByRole('link', { name: 'Edit topic' })).toHaveAttribute('href', '/settings#topic');
  expect(screen.getByRole('link', { name: 'Manage in Settings' })).toHaveAttribute('href', '/settings');
  expect(screen.queryByRole('textbox', { name: 'Research topic' })).not.toBeInTheDocument();
});
it('filters the feed to topic matches from the sidebar and back', async () => {
  vi.mocked(researchApi.topic).mockResolvedValue(topic);
  renderFeed('/following?only=topic');
  await waitFor(() => expect(researchApi.following).toHaveBeenCalledWith(0, expect.objectContaining({ topicOnly: true })));
  expect(await screen.findByText(/Showing only papers about \u201creal-time video generation\u201d/)).toBeInTheDocument();
  const row = screen.getByRole('link', { name: /^Topic real-time video generation$/ });
  expect(row).toHaveAttribute('aria-current', 'true');
  expect(row).toHaveAttribute('href', '/following');
  expect(screen.getByRole('link', { name: 'Show everything you follow' })).toHaveAttribute('href', '/following');
});
it('prompts accounts without a topic to describe one above their follows feed', async () => {
  renderFeed();
  expect(await screen.findByRole('textbox', { name: 'Research topic' })).toBeInTheDocument();
  expect(await screen.findByText('A paper')).toBeInTheDocument();
});
it('shows the feed for an account that follows only a topic', async () => {
  vi.mocked(researchApi.follows).mockResolvedValue([]);
  vi.mocked(researchApi.topic).mockResolvedValue({ ...topic, status: 'running', judged: 200, total: 4700 });
  renderFeed();
  expect(await screen.findByText(/Finding papers about \u201creal-time video generation\u201d/)).toBeInTheDocument();
  expect(await screen.findByText('A paper')).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Build your personal research feed' })).not.toBeInTheDocument();
});

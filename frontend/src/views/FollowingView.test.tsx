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
const login = vi.hoisted(() => ({ hfLoginUrl: vi.fn(() => window.location.href) }));
vi.mock('@/components/HfSignInButton', async importOriginal => ({
  ...await importOriginal<typeof import('@/components/HfSignInButton')>(), hfLoginUrl: login.hfLoginUrl,
}));
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
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); sessionStorage.clear(); login.hfLoginUrl.mockClear(); });
it('renders following in the existing tab row with standard paper cards and thumbnails', async () => {
  const { container } = renderFeed();
  await screen.findByText('A paper');
  expect(container.querySelector('.paper-card .paper-thumb-wrap img')).toHaveAttribute('src', expect.stringContaining('/api/thumbnails/example.png'));
  expect(container.querySelector('.paper-authors')).toHaveTextContent('An Author');
  expect(container.querySelector('.paper-follow-reason')).toHaveTextContent('Because you follow Task');
  expect(screen.getByText('Full abstract.')).toBeInTheDocument();
  const tab = screen.getByRole('button', { name: 'following' });
  expect(tab).toHaveClass('active');
  expect(tab.parentElement?.textContent).toBe('trendingfollowing');
  expect(screen.queryByText('Discover')).not.toBeInTheDocument();
  expect(papersApi.list).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'trending' }));
  expect(await screen.findByText('No papers in this window.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'trending' })).toHaveClass('active');
  expect(papersApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ order_by: 'trending' }));
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
it('asks signed-out visitors for a topic and signs them in when they submit it', async () => {
  auth.user = null;
  renderFeed();
  expect(await screen.findByRole('dialog', { name: 'Follow a topic' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Build your personal research feed', hidden: true })).toBeInTheDocument();
  expect(screen.queryByText(/Sign in/)).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /Browse tasks/ })).not.toBeInTheDocument();
  const input = screen.getByRole('textbox', { name: 'Research topic' });
  fireEvent.change(input, { target: { value: '  speculative   decoding ' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(login.hfLoginUrl).toHaveBeenCalledWith('/following');
  expect(sessionStorage.getItem('pwc:following-pending-topic')).toBe('speculative decoding');
  expect(researchApi.following).not.toHaveBeenCalled();
});

it('saves the topic a visitor submitted before signing in', async () => {
  sessionStorage.setItem('pwc:following-pending-topic', 'speculative decoding');
  vi.spyOn(researchApi, 'setTopic').mockResolvedValue({ ...topic, text: 'speculative decoding', status: 'pending' });
  renderFeed();
  await waitFor(() => expect(researchApi.setTopic).toHaveBeenCalledTimes(1));
  expect(researchApi.setTopic).toHaveBeenCalledWith('speculative decoding');
  await waitFor(() => expect(sessionStorage.getItem('pwc:following-pending-topic')).toBeNull());
});

it('keeps a pre-sign-in topic and offers a retry when saving it fails', async () => {
  sessionStorage.setItem('pwc:following-pending-topic', 'speculative decoding');
  vi.spyOn(researchApi, 'setTopic').mockRejectedValueOnce(new Error('down'))
    .mockResolvedValueOnce({ ...topic, text: 'speculative decoding', status: 'pending' });
  renderFeed();
  expect(await screen.findByText(/Could not follow “speculative decoding”/)).toBeInTheDocument();
  expect(sessionStorage.getItem('pwc:following-pending-topic')).toBe('speculative decoding');
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  await waitFor(() => expect(sessionStorage.getItem('pwc:following-pending-topic')).toBeNull());
  expect(researchApi.setTopic).toHaveBeenCalledTimes(2);
});

it('drops a stashed guest topic once another topic is saved', async () => {
  sessionStorage.setItem('pwc:following-pending-topic', 'old guest topic');
  vi.spyOn(researchApi, 'setTopic').mockRejectedValueOnce(new Error('down'))
    .mockResolvedValueOnce({ ...topic, status: 'pending' });
  renderFeed();
  expect(await screen.findByText(/Could not follow “old guest topic”/)).toBeInTheDocument();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Follow a topic' }));
  fireEvent.change(screen.getByRole('textbox', { name: 'Research topic' }), { target: { value: 'real-time video generation' } });
  fireEvent.click(screen.getByRole('button', { name: 'Follow topic' }));
  await waitFor(() => expect(sessionStorage.getItem('pwc:following-pending-topic')).toBeNull());
});

it('explains how to follow when a signed-in account follows nothing yet', async () => {
  vi.mocked(researchApi.follows).mockResolvedValue([]);
  vi.mocked(researchApi.following).mockResolvedValue([]);
  vi.mocked(catalogApi.topTasks).mockResolvedValue([
    { id: '1', name: 'Object Detection', slug: 'object-detection', paper_count: 10 } as never,
  ]);
  vi.spyOn(researchApi, 'setTopic').mockResolvedValue({ ...topic, status: 'pending' });
  renderFeed();
  expect(await screen.findByRole('dialog', { name: 'Follow a topic' })).toBeInTheDocument();
  expect(await screen.findByRole('link', { name: 'Object Detection', hidden: true })).toHaveAttribute('href', '/tasks/object-detection');
  expect(screen.queryByText(/match these filters/)).not.toBeInTheDocument();
  expect(screen.getAllByRole('textbox', { name: 'Research topic' })).toHaveLength(1);
  fireEvent.change(screen.getByRole('textbox', { name: 'Research topic' }), { target: { value: 'real-time video generation' } });
  fireEvent.click(screen.getByRole('button', { name: 'Follow topic' }));
  await waitFor(() => expect(researchApi.setTopic).toHaveBeenCalledWith('real-time video generation'));
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

it('sends the date filter to Following without resource filters', async () => {
  renderFeed();
  await screen.findByText('A paper');
  // Following defaults to its 30-day window.
  expect(screen.getByRole('button', { name: 'Last Month' })).toHaveClass('active');
  const [, defaults] = vi.mocked(researchApi.following).mock.calls[0];
  expect(defaults?.startDate).toBeDefined();
  expect(screen.queryByRole('button', { name: /Has code/ })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Has artifacts/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'All Time' }));
  await vi.waitFor(() => expect(researchApi.following).toHaveBeenLastCalledWith(0, {
    startDate: undefined, endDate: undefined, topicOnly: false,
  }));
});

it('keeps the date range when switching from the public feed to Following', async () => {
  renderFeed('/?start_date=2026-09-01&end_date=2026-09-30&order_by=date_published');
  await screen.findByText('No papers in this window.');
  fireEvent.click(screen.getByRole('button', { name: 'following' }));
  await screen.findByText('A paper');
  expect(researchApi.following).toHaveBeenLastCalledWith(0, {
    startDate: '2026-09-01', endDate: '2026-09-30', topicOnly: false,
  });
});

it('groups followed entities under one kind badge each in the sidebar', async () => {
  vi.mocked(researchApi.follows).mockResolvedValue([
    { kind: 'organization', entity_id: 7, name: 'Liquid AI', url: '/organizations/liquid-ai', created_at: '' },
    { kind: 'task', entity_id: 1, name: 'Coding Agents', url: '/tasks/coding-agents', created_at: '' },
    { kind: 'task', entity_id: 2, name: 'Robotics', url: '/tasks/robotics', created_at: '' },
  ]);
  const { container } = renderFeed();
  await screen.findByRole('link', { name: 'Liquid AI' });
  const groups = [...container.querySelectorAll('.sidebar-follow-group')];
  expect(groups.map(group => group.textContent)).toEqual(['TasksCoding AgentsRobotics', 'OrgsLiquid AI']);
  expect(screen.getByRole('link', { name: 'Liquid AI' })).toHaveAttribute('href', '/organizations/liquid-ai');
  expect(container.querySelector('.sidebar-section-top-domains')).toBeNull();
});

it('keeps domain lists out of the Following sidebar while follows load', () => {
  vi.mocked(researchApi.follows).mockReturnValue(new Promise(() => {}));
  const { container } = renderFeed();
  expect(screen.getByText('You follow')).toBeInTheDocument();
  expect(container.querySelector('.sidebar-section-top-domains')).toBeNull();
});

it('lists the topic first in the sidebar as a filter with an edit button, and links Settings below', async () => {
  vi.mocked(researchApi.topic).mockResolvedValue(topic);
  renderFeed();
  const row = await screen.findByRole('link', { name: /^Topic real-time video generation$/ });
  expect(row).toHaveAttribute('href', '/following?only=topic');
  expect(screen.getByRole('button', { name: 'Edit topic' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Manage in Settings' })).toHaveAttribute('href', '/settings');
  expect(screen.queryByRole('textbox', { name: 'Research topic' })).not.toBeInTheDocument();
});
it('edits the topic in place on /following and closes the editor after saving', async () => {
  vi.mocked(researchApi.topic).mockResolvedValue(topic);
  vi.spyOn(researchApi, 'setTopic').mockResolvedValue({ ...topic, text: 'video world models' });
  Element.prototype.scrollIntoView = vi.fn();
  renderFeed();
  fireEvent.click(await screen.findByRole('button', { name: 'Edit topic' }));
  const input = await screen.findByRole('textbox', { name: 'Research topic' });
  expect(input).toHaveValue('real-time video generation');
  fireEvent.change(input, { target: { value: 'video world models' } });
  fireEvent.click(screen.getByRole('button', { name: 'Update topic' }));
  await waitFor(() => expect(researchApi.setTopic).toHaveBeenCalledWith('video world models'));
  await waitFor(() => expect(screen.queryByRole('textbox', { name: 'Research topic' })).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: 'Edit topic' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
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
it('offers accounts without a topic a pop-up to describe one above their follows feed', async () => {
  renderFeed();
  fireEvent.click(await screen.findByRole('button', { name: 'Follow a topic' }));
  expect(await screen.findByRole('textbox', { name: 'Research topic' })).toBeInTheDocument();
  expect(await screen.findByText('A paper')).toBeInTheDocument();
});
it('leaves the topic pop-up closed after the only topic is removed', async () => {
  vi.mocked(researchApi.follows).mockResolvedValue([]);
  vi.mocked(researchApi.topic).mockResolvedValue(topic);
  vi.spyOn(researchApi, 'clearTopic').mockResolvedValue(undefined);
  renderFeed();
  fireEvent.click(await screen.findByRole('button', { name: 'Edit topic' }));
  vi.mocked(researchApi.topic).mockResolvedValue(null);
  fireEvent.click(await screen.findByRole('button', { name: 'Remove' }));
  expect(await screen.findByRole('heading', { name: 'Build your personal research feed', hidden: true })).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(screen.getByRole('button', { name: 'Follow a topic' })).toBeInTheDocument();
});
it('shows the feed for an account that follows only a topic', async () => {
  vi.mocked(researchApi.follows).mockResolvedValue([]);
  vi.mocked(researchApi.topic).mockResolvedValue({ ...topic, status: 'running', judged: 200, total: 4700 });
  renderFeed();
  expect(await screen.findByText(/Finding papers about \u201creal-time video generation\u201d/)).toBeInTheDocument();
  expect(await screen.findByText('A paper')).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Build your personal research feed' })).not.toBeInTheDocument();
});

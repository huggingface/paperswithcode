import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { researchApi, TOPIC_LIMIT } from '@/lib/api/research';
import { ApiError } from '@/lib/apiTransport';
import { catalogApi } from '@/lib/api/catalog';
import { papersApi } from '@/lib/api/papers';
import FollowingView from './FollowingView';
import FeedView from './FeedView';

const auth = vi.hoisted(() => ({ user: { hf_subject: 'alice', username: 'alice' } as { hf_subject: string; username: string } | null, isLoading: false }));
vi.mock('@/lib/authContext', () => ({ useAuth: () => auth, useOptionalAuth: () => auth }));
const login = vi.hoisted(() => ({ hfLoginUrl: vi.fn(() => window.location.href) }));
vi.mock('@/lib/apiUrl', async importOriginal => ({
  ...await importOriginal<typeof import('@/lib/apiUrl')>(), hfLoginUrl: login.hfLoginUrl,
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
  vi.spyOn(researchApi, 'followSuggestions').mockResolvedValue({ authors: [
    { entity_id: 266, name: 'Yann LeCun', url: '/authors/266', image_url: '/api/v1/authors/266/photo/abc.jpg' },
    { entity_id: 25, name: 'Yoshua Bengio', url: '/authors/25', image_url: null },
    { entity_id: 264, name: 'Kaiming He', url: '/authors/264', image_url: null },
  ], organizations: [] });
  vi.spyOn(catalogApi, 'trendingMethods').mockResolvedValue({ results: [], recent_days: 7, baseline_days: 30 } as never);
  vi.spyOn(papersApi, 'list').mockResolvedValue({ count: 0, results: [], next_page: null, previous_page: null });
  vi.spyOn(researchApi, 'follows').mockResolvedValue([
    { kind: 'task', entity_id: 1, name: 'Task', url: '/tasks/task', created_at: '' },
  ]);
  vi.spyOn(researchApi, 'following').mockResolvedValue([{ paper, paper_key: 'arxiv:2610.12345',
    title: paper.title, url: '/paper/2610.12345', summary: 'Short summary.', published: paper.published,
    reasons: ['Task'], scores: [] }]);
  vi.spyOn(researchApi, 'topics').mockResolvedValue([]);
  vi.spyOn(researchApi, 'featuredTopics').mockResolvedValue([]);
  vi.spyOn(researchApi, 'topicMatches').mockResolvedValue([]);
});
const REWORD = 'Reword Real-time video generation';
const topic = { id: 1, text: 'real-time video generation', label: null, set_at: '2026-10-28T10:00:00Z', status: 'done' as const,
  judged: 10, total: 10, suggestions: [], is_public: true, is_creator: true };
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
it('asks signed-out visitors for a topic and picks, and signs them in when they submit', async () => {
  auth.user = null;
  vi.mocked(catalogApi.trendingTasks).mockResolvedValue({ results: [
    { id: '7', name: 'Object Detection', slug: 'object-detection', share_lift: 2 } as never,
  ], recent_days: 7, baseline_days: 30 });
  renderFeed();
  expect(await screen.findByRole('dialog', { name: 'Build your research feed' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Build your personal research feed', hidden: true })).toBeInTheDocument();
  expect(screen.queryByText(/Sign in/)).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /Browse tasks/ })).not.toBeInTheDocument();
  const input = screen.getByRole('textbox', { name: 'Research topic' });
  fireEvent.change(input, { target: { value: '  speculative   decoding ' } });
  fireEvent.click(await screen.findByRole('button', { name: 'Object Detection' }));
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(login.hfLoginUrl).toHaveBeenCalledWith('/following');
  expect(sessionStorage.getItem('pwc:following-pending-topic')).toBe('speculative decoding');
  expect(JSON.parse(sessionStorage.getItem('pwc:following-pending-follows') ?? '[]'))
    .toEqual([{ kind: 'task', id: '7', name: 'Object Detection', follow: true }]);
  expect(researchApi.following).not.toHaveBeenCalled();
});

it('saves the topic a visitor submitted before signing in', async () => {
  sessionStorage.setItem('pwc:following-pending-topic', 'speculative decoding');
  vi.spyOn(researchApi, 'addTopic').mockResolvedValue({ ...topic, text: 'speculative decoding', status: 'pending' });
  renderFeed();
  await waitFor(() => expect(researchApi.addTopic).toHaveBeenCalledTimes(1));
  expect(researchApi.addTopic).toHaveBeenCalledWith('speculative decoding');
  await waitFor(() => expect(sessionStorage.getItem('pwc:following-pending-topic')).toBeNull());
});

it('follows the tasks and methods a visitor picked before signing in', async () => {
  sessionStorage.setItem('pwc:following-pending-follows', JSON.stringify([{ kind: 'task', id: '7', name: 'Object Detection' }]));
  vi.spyOn(researchApi, 'setFollow').mockRejectedValueOnce(new Error('down')).mockResolvedValueOnce(undefined);
  renderFeed();
  fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));
  expect(screen.getByText(/Could not follow Object Detection/)).toBeInTheDocument();
  await waitFor(() => expect(sessionStorage.getItem('pwc:following-pending-follows')).toBeNull());
  expect(researchApi.setFollow).toHaveBeenCalledTimes(2);
  expect(researchApi.setFollow).toHaveBeenLastCalledWith('task', '7', true);
});

it('keeps the pop-up closed while saving picks a guest made before signing in', async () => {
  sessionStorage.setItem('pwc:following-pending-follows', JSON.stringify([{ kind: 'author', id: '266', name: 'Yann LeCun' }]));
  vi.mocked(researchApi.follows).mockResolvedValue([]);
  vi.mocked(researchApi.following).mockResolvedValue([]);
  vi.spyOn(researchApi, 'setFollow').mockResolvedValue(undefined);
  renderFeed();
  await waitFor(() => expect(sessionStorage.getItem('pwc:following-pending-follows')).toBeNull());
  expect(await screen.findByRole('button', { name: 'Build your feed' })).toBeInTheDocument();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('saves the topic even when a picked follow fails, and reports the failure', async () => {
  vi.mocked(researchApi.follows).mockResolvedValue([]);
  vi.mocked(researchApi.following).mockResolvedValue([]);
  vi.spyOn(researchApi, 'setFollow').mockRejectedValue(new Error('down'));
  vi.spyOn(researchApi, 'addTopic').mockResolvedValue({ ...topic, status: 'pending' });
  renderFeed();
  fireEvent.click(await screen.findByRole('button', { name: 'Yann LeCun' }));
  fireEvent.change(screen.getByRole('textbox', { name: 'Research topic' }), { target: { value: 'real-time video generation' } });
  fireEvent.click(screen.getByRole('button', { name: 'Follow' }));
  await waitFor(() => expect(researchApi.addTopic).toHaveBeenCalledWith('real-time video generation'));
  expect(await screen.findByText('Could not save your feed. Please try again.')).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

it('retries a topic whose backfill failed from the pop-up', async () => {
  vi.mocked(researchApi.topics).mockResolvedValue([{ ...topic, status: 'failed' }]);
  vi.spyOn(researchApi, 'updateTopic').mockResolvedValue({ ...topic, status: 'pending' });
  renderFeed();
  fireEvent.click(await screen.findByRole('button', { name: 'Edit feed' }));
  fireEvent.click(await screen.findByRole('button', { name: REWORD }));
  fireEvent.click(await screen.findByRole('button', { name: 'Retry' }));
  await waitFor(() => expect(researchApi.updateTopic).toHaveBeenCalledWith(1, 'real-time video generation'));
});
it('keeps a pre-sign-in topic and offers a retry when saving it fails', async () => {
  sessionStorage.setItem('pwc:following-pending-topic', 'speculative decoding');
  vi.spyOn(researchApi, 'addTopic').mockRejectedValueOnce(new Error('down'))
    .mockResolvedValueOnce({ ...topic, text: 'speculative decoding', status: 'pending' });
  renderFeed();
  expect(await screen.findByText(/Could not follow “speculative decoding”/)).toBeInTheDocument();
  expect(sessionStorage.getItem('pwc:following-pending-topic')).toBe('speculative decoding');
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  await waitFor(() => expect(sessionStorage.getItem('pwc:following-pending-topic')).toBeNull());
  expect(researchApi.addTopic).toHaveBeenCalledTimes(2);
});

it('explains and drops a pre-sign-in topic the server refuses', async () => {
  sessionStorage.setItem('pwc:following-pending-topic', 'harness engineering');
  const body = JSON.stringify({ detail: '“harness engineering” is already a task; follow Harness Engineering instead' });
  vi.spyOn(researchApi, 'addTopic').mockRejectedValueOnce(new ApiError(new Response(body, { status: 409 }), body));
  renderFeed();
  expect(await screen.findByText(/follow Harness Engineering instead\./)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  expect(sessionStorage.getItem('pwc:following-pending-topic')).toBeNull();
});

it('drops a stashed guest topic once another topic is saved', async () => {
  sessionStorage.setItem('pwc:following-pending-topic', 'old guest topic');
  vi.spyOn(researchApi, 'addTopic').mockRejectedValueOnce(new Error('down'))
    .mockResolvedValueOnce({ ...topic, status: 'pending' });
  renderFeed();
  expect(await screen.findByText(/Could not follow “old guest topic”/)).toBeInTheDocument();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Edit feed' }));
  fireEvent.change(screen.getByRole('textbox', { name: 'Research topic' }), { target: { value: 'real-time video generation' } });
  fireEvent.click(screen.getByRole('button', { name: 'Follow' }));
  await waitFor(() => expect(sessionStorage.getItem('pwc:following-pending-topic')).toBeNull());
});

it('explains how to follow when a signed-in account follows nothing yet', async () => {
  vi.mocked(researchApi.follows).mockResolvedValue([]);
  vi.mocked(researchApi.following).mockResolvedValue([]);
  vi.mocked(catalogApi.trendingTasks).mockResolvedValue({ results: [
    { id: '7', name: 'Object Detection', slug: 'object-detection', share_lift: 2 } as never,
  ], recent_days: 7, baseline_days: 30 });
  vi.mocked(catalogApi.trendingMethods).mockResolvedValue({ results: [
    { id: '9', name: 'LoRA', slug: 'lora' },
  ], recent_days: 7, baseline_days: 30 } as never);
  vi.mocked(researchApi.followSuggestions).mockResolvedValue({ authors: [
    { entity_id: 266, name: 'Yann LeCun', url: '/authors/266', image_url: '/api/v1/authors/266/photo/abc.jpg' },
  ], organizations: [
    { entity_id: 1, name: 'Microsoft', url: '/orgs/microsoft', image_url: null },
    { entity_id: 3, name: 'NVIDIA', url: '/orgs/nvidia', image_url: '/api/v1/organizations/nvidia/logo/abc.png' },
  ] });
  vi.spyOn(researchApi, 'addTopic').mockResolvedValue({ ...topic, status: 'pending' });
  vi.spyOn(researchApi, 'setFollow').mockResolvedValue(undefined);
  renderFeed();
  expect(await screen.findByRole('dialog', { name: 'Build your research feed' })).toBeInTheDocument();
  expect(screen.queryByText(/match these filters/)).not.toBeInTheDocument();
  expect(screen.getAllByRole('textbox', { name: 'Research topic' })).toHaveLength(1);
  const task = await screen.findByRole('button', { name: 'Object Detection' });
  expect(task).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(task);
  expect(task).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(await screen.findByRole('button', { name: 'LoRA' }));
  fireEvent.click(screen.getByRole('button', { name: 'Yann LeCun' }));
  const nvidia = await screen.findByRole('button', { name: 'NVIDIA' });
  expect(nvidia.querySelector('img')).toHaveAttribute('src', '/api/v1/organizations/nvidia/logo/abc.png');
  fireEvent.click(nvidia);
  fireEvent.change(screen.getByRole('textbox', { name: 'Research topic' }), { target: { value: 'real-time video generation' } });
  fireEvent.click(screen.getByRole('button', { name: 'Follow' }));
  await waitFor(() => expect(researchApi.addTopic).toHaveBeenCalledWith('real-time video generation'));
  expect(researchApi.setFollow).toHaveBeenCalledWith('task', '7', true);
  expect(researchApi.setFollow).toHaveBeenCalledWith('method', '9', true);
  expect(researchApi.setFollow).toHaveBeenCalledWith('author', '266', true);
  expect(researchApi.setFollow).toHaveBeenCalledWith('organization', '3', true);
});

it('fills two rows per group with suggestions, then links to browse the rest', async () => {
  // jsdom has no layout: lay chips out four per row.
  vi.spyOn(HTMLElement.prototype, 'offsetTop', 'get').mockImplementation(function (this: HTMLElement) {
    const visible = [...(this.parentElement?.children ?? [])].filter(element => !(element as HTMLElement).hidden);
    return Math.floor(visible.indexOf(this) / 4) * 30;
  });
  vi.mocked(researchApi.follows).mockResolvedValue([]);
  vi.mocked(researchApi.following).mockResolvedValue([]);
  vi.mocked(catalogApi.trendingTasks).mockResolvedValue({ results: Array.from({ length: 8 }, (_, i) => (
    { id: String(i + 1), name: `Task ${i + 1}`, slug: `task-${i + 1}`, share_lift: 2 } as never)), recent_days: 7, baseline_days: 30 });
  renderFeed();
  // Eight tasks and the browse link need three rows, so the last task gives way.
  expect(await screen.findByRole('button', { name: 'Task 7' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Task 8' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Yann LeCun' }).querySelector('img'))
    .toHaveAttribute('src', '/api/v1/authors/266/photo/abc.jpg');
  // Authors without a photo show their initials.
  expect(screen.getByRole('button', { name: 'Kaiming He' })).toHaveTextContent('KH');
  expect(screen.queryByRole('button', { name: 'Fei-Fei Li' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Browse tasks' })).toHaveAttribute('href', '/tasks');
});

it('shows what the account already follows first, and unfollows on save', async () => {
  vi.mocked(researchApi.follows).mockResolvedValue([
    { kind: 'task', entity_id: 895, name: 'Long-Horizon Agents', url: '/tasks/long-horizon-agents', created_at: '' },
    { kind: 'benchmark', entity_id: 12, name: 'SWE-bench Verified', url: '/benchmark/swe-bench-verified', created_at: '' },
  ]);
  vi.mocked(catalogApi.trendingTasks).mockResolvedValue({ results: [
    { id: '895', name: 'Long-Horizon Agents', slug: 'long-horizon-agents', share_lift: 2 } as never,
    { id: '7', name: 'Object Detection', slug: 'object-detection', share_lift: 2 } as never,
  ], recent_days: 7, baseline_days: 30 });
  vi.spyOn(researchApi, 'setFollow').mockResolvedValue(undefined);
  renderFeed();
  fireEvent.click(await screen.findByRole('button', { name: 'Edit feed' }));
  expect(await screen.findByRole('dialog', { name: 'Edit your research feed' })).toBeInTheDocument();
  const followed = await screen.findByRole('button', { name: 'Long-Horizon Agents' });
  expect(followed).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getAllByRole('button', { name: 'Long-Horizon Agents' })).toHaveLength(1);
  expect(screen.getByRole('button', { name: 'Object Detection' })).toHaveAttribute('aria-pressed', 'false');
  expect(screen.getByRole('button', { name: 'SWE-bench Verified' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('link', { name: 'Browse benchmarks' })).toHaveAttribute('href', '/tasks');
  fireEvent.click(followed);
  expect(followed).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(researchApi.setFollow).toHaveBeenCalledWith('task', '895', false));
});

it('keeps a chip selected when its follow saved but the topic did not', async () => {
  vi.mocked(catalogApi.trendingTasks).mockResolvedValue({ results: [
    { id: '7', name: 'Object Detection', slug: 'object-detection', share_lift: 2 } as never,
  ], recent_days: 7, baseline_days: 30 });
  vi.spyOn(researchApi, 'setFollow').mockImplementation(async () => {
    vi.mocked(researchApi.follows).mockResolvedValue([
      { kind: 'task', entity_id: 1, name: 'Task', url: '/tasks/task', created_at: '' },
      { kind: 'task', entity_id: 7, name: 'Object Detection', url: '/tasks/object-detection', created_at: '' },
    ]);
  });
  vi.spyOn(researchApi, 'addTopic').mockRejectedValue(new Error('down'));
  renderFeed();
  fireEvent.click(await screen.findByRole('button', { name: 'Edit feed' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Object Detection' }));
  fireEvent.change(screen.getByRole('textbox', { name: 'Research topic' }), { target: { value: 'real-time video generation' } });
  fireEvent.click(screen.getByRole('button', { name: 'Follow' }));
  expect(await screen.findByText('Could not save your feed. Please try again.')).toBeInTheDocument();
  await waitFor(() => expect(vi.mocked(researchApi.follows).mock.calls.length).toBeGreaterThanOrEqual(2));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Object Detection' })).toHaveAttribute('aria-pressed', 'true'));
  fireEvent.click(screen.getByRole('button', { name: 'Follow' }));
  await waitFor(() => expect(researchApi.addTopic).toHaveBeenCalledTimes(2));
  expect(researchApi.setFollow).toHaveBeenCalledTimes(1);
});

it('keeps the filter hint when follows exist but nothing matches', async () => {
  vi.mocked(researchApi.following).mockResolvedValue([]);
  renderFeed();
  expect(await screen.findByText(/No papers from your topics or follows match these filters/)).toBeInTheDocument();
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
    startDate: undefined, endDate: undefined, topicOnly: false, topicIds: [], follows: [],
  }));
});

it('keeps the date range when switching from the public feed to Following', async () => {
  renderFeed('/?start_date=2026-09-01&end_date=2026-09-30&order_by=date_published');
  await screen.findByText('No papers in this window.');
  fireEvent.click(screen.getByRole('button', { name: 'following' }));
  await screen.findByText('A paper');
  expect(researchApi.following).toHaveBeenLastCalledWith(0, {
    startDate: '2026-09-01', endDate: '2026-09-30', topicOnly: false, topicIds: [], follows: [],
  });
});

it('shows topics, then follows grouped by kind, as filter bubbles with the homepage sidebar', async () => {
  vi.mocked(researchApi.topics).mockResolvedValue([topic]);
  vi.mocked(researchApi.follows).mockResolvedValue([
    { kind: 'method', entity_id: 4, name: 'LoRA', url: '/methods/lora', created_at: '2026-10-02' },
    { kind: 'task', entity_id: 1, name: 'Coding Agents', url: '/tasks/coding-agents', created_at: '2026-10-01' },
    { kind: 'task', entity_id: 2, name: 'Video Inpainting', url: '/tasks/video-inpainting', created_at: '2026-10-03',
      parent_slug: 'image-inpainting' },
    { kind: 'organization', entity_id: 7, name: 'Liquid AI', url: '/orgs/liquid-ai', created_at: '2026-09-01',
      image_url: '/logo.png' },
  ]);
  const { container } = renderFeed();
  const row = await screen.findByRole('navigation', { name: 'Filter your feed' });
  await within(row).findByRole('link', { name: 'Liquid AI' });
  expect([...row.children].map(bubble => bubble.textContent)).toEqual([
    'All', 'Real-time video generation', 'Liquid AI', 'Video Inpainting', 'Coding Agents', 'LoRA', 'Edit feed',
  ]);
  expect(within(row).getByRole('link', { name: 'All' })).toHaveAttribute('aria-current', 'true');
  expect(within(row).getByRole('link', { name: 'Liquid AI' })).toHaveAttribute('href', '/following?follow=organization%3A7');
  expect(within(row).getByRole('link', { name: 'Liquid AI' }).querySelector('img')).toHaveAttribute('src', '/logo.png');
  // Tasks borrow the /tasks icons; methods and topics are text only.
  expect(within(row).getByRole('link', { name: 'Coding Agents' }).querySelector('svg')).not.toBeNull();
  expect(within(row).getByRole('link', { name: 'LoRA' }).querySelector('svg, img')).toBeNull();
  expect(within(row).getByRole('link', { name: 'Real-time video generation' }).querySelector('svg, img')).toBeNull();
  expect(within(row).getByRole('link', { name: 'Real-time video generation' })).toHaveAttribute('href', '/following?topic=1');
  expect(screen.queryByText('You follow')).not.toBeInTheDocument();
  expect(container.querySelector('.sidebar-section-top-domains')).not.toBeNull();
});
it('collapses a long row behind +N more, keeping selected bubbles visible', async () => {
  vi.mocked(researchApi.follows).mockResolvedValue(Array.from({ length: 15 }, (_, i) => (
    { kind: 'task' as const, entity_id: i + 1, name: `Task ${i + 1}`, url: `/tasks/task-${i + 1}`, created_at: `2026-10-${String(30 - i).padStart(2, '0')}` })));
  renderFeed('/following?follow=task:15');
  const row = await screen.findByRole('navigation', { name: 'Filter your feed' });
  expect(await within(row).findByRole('link', { name: 'Task 15' })).toHaveAttribute('aria-current', 'true');
  expect(within(row).queryByRole('link', { name: 'Task 13' })).not.toBeInTheDocument();
  fireEvent.click(within(row).getByRole('button', { name: '+2 more' }));
  expect(within(row).getByRole('link', { name: 'Task 13' })).toBeInTheDocument();
});
it('hides +N more when every bubble past the fold is selected', async () => {
  vi.mocked(researchApi.follows).mockResolvedValue(Array.from({ length: 15 }, (_, i) => (
    { kind: 'task' as const, entity_id: i + 1, name: `Task ${i + 1}`, url: `/tasks/task-${i + 1}`, created_at: `2026-10-${String(30 - i).padStart(2, '0')}` })));
  renderFeed('/following?follow=task:13&follow=task:14&follow=task:15');
  const row = await screen.findByRole('navigation', { name: 'Filter your feed' });
  expect(await within(row).findByRole('link', { name: 'Task 13' })).toHaveAttribute('aria-current', 'true');
  expect(within(row).queryByRole('button', { name: /more/ })).not.toBeInTheDocument();
});
it('filters the feed to one follow from its bubble', async () => {
  renderFeed('/following?follow=task:1');
  await waitFor(() => expect(researchApi.following).toHaveBeenCalledWith(0, expect.objectContaining({ follows: ['task:1'], topicIds: [] })));
  const bubble = await screen.findByRole('link', { name: 'Task' });
  expect(bubble).toHaveAttribute('aria-current', 'true');
  expect(bubble).toHaveAttribute('href', '/following');
});
it('selects several bubbles at once and shows papers matching any of them', async () => {
  vi.mocked(researchApi.topics).mockResolvedValue([topic, { ...topic, id: 2, text: 'speculative decoding' }]);
  renderFeed('/following?topic=1');
  const row = await screen.findByRole('navigation', { name: 'Filter your feed' });
  // Unselected bubbles add themselves to the selection; selected ones remove themselves.
  expect(await within(row).findByRole('link', { name: 'Speculative decoding' })).toHaveAttribute('href', '/following?topic=1&topic=2');
  expect(await within(row).findByRole('link', { name: 'Task' })).toHaveAttribute('href', '/following?topic=1&follow=task%3A1');
  fireEvent.click(within(row).getByRole('link', { name: 'Task' }));
  await waitFor(() => expect(researchApi.following).toHaveBeenLastCalledWith(0, expect.objectContaining({ topicIds: [1], follows: ['task:1'] })));
  expect(within(row).getByRole('link', { name: 'Task' })).toHaveAttribute('aria-current', 'true');
  expect(within(row).getByRole('link', { name: 'Real-time video generation' })).toHaveAttribute('aria-current', 'true');
  expect(within(row).getByRole('link', { name: 'Real-time video generation' })).toHaveAttribute('href', '/following?follow=task%3A1');
  expect(within(row).getByRole('link', { name: 'All' })).not.toHaveAttribute('aria-current');
  fireEvent.click(within(row).getByRole('link', { name: 'All' }));
  await waitFor(() => expect(researchApi.following).toHaveBeenLastCalledWith(0, expect.objectContaining({ topicIds: [], follows: [] })));
});
it('drops a filter whose follow is gone, keeping the rest of the selection', async () => {
  renderFeed('/following?follow=task:99');
  await waitFor(() => expect(researchApi.following).toHaveBeenLastCalledWith(0, expect.objectContaining({ follows: [] })));
  expect(await screen.findByRole('link', { name: 'All' })).toHaveAttribute('aria-current', 'true');
  cleanup();
  renderFeed('/following?follow=task:99&follow=task:1');
  await waitFor(() => expect(researchApi.following).toHaveBeenLastCalledWith(0, expect.objectContaining({ follows: ['task:1'] })));
});
it('opens the feed pop-up from ?edit=1, as Settings links it', async () => {
  renderFeed('/following?edit=1');
  expect(await screen.findByRole('dialog', { name: 'Edit your research feed' })).toBeInTheDocument();
});
it('rewords a topic from the pop-up and closes it after saving', async () => {
  vi.mocked(researchApi.topics).mockResolvedValue([topic]);
  vi.spyOn(researchApi, 'updateTopic').mockResolvedValue({ ...topic, text: 'video world models' });
  renderFeed();
  fireEvent.click(await screen.findByRole('button', { name: 'Edit feed' }));
  fireEvent.click(await screen.findByRole('button', { name: REWORD }));
  const input = await screen.findByRole('textbox', { name: 'Research topic' });
  expect(input).toHaveValue('real-time video generation');
  fireEvent.change(input, { target: { value: 'video world models' } });
  fireEvent.click(screen.getByRole('button', { name: 'Update topic' }));
  await waitFor(() => expect(researchApi.updateTopic).toHaveBeenCalledWith(1, 'video world models'));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
});
it('adds another topic from Edit feed and can drop an existing one in the same save', async () => {
  vi.mocked(researchApi.topics).mockResolvedValue([topic, { ...topic, id: 2, text: 'speculative decoding' }]);
  vi.spyOn(researchApi, 'addTopic').mockResolvedValue({ ...topic, id: 3, text: 'robot learning' });
  vi.spyOn(researchApi, 'removeTopic').mockResolvedValue(undefined);
  renderFeed();
  fireEvent.click(await screen.findByRole('button', { name: 'Edit feed' }));
  const input = await screen.findByRole('textbox', { name: 'Research topic' });
  expect(input).toHaveValue('');
  const other = screen.getByRole('button', { name: 'Speculative decoding' });
  expect(other).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(other);
  fireEvent.change(input, { target: { value: 'robot learning' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(researchApi.addTopic).toHaveBeenCalledWith('robot learning'));
  expect(researchApi.removeTopic).toHaveBeenCalledWith(2);
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
});
it('keeps Edit feed at the topic limit and explains it', async () => {
  vi.mocked(researchApi.topics).mockResolvedValue(Array.from({ length: TOPIC_LIMIT }, (_, i) => ({ ...topic, id: i + 1, text: `topic ${i}` })));
  renderFeed();
  fireEvent.click(await screen.findByRole('button', { name: 'Edit feed' }));
  expect(await screen.findByText(/You follow 10 topics, the most allowed/)).toBeInTheDocument();
});
it('filters the feed to one topic from its bubble and back', async () => {
  vi.mocked(researchApi.topics).mockResolvedValue([topic, { ...topic, id: 2, text: 'speculative decoding' }]);
  renderFeed('/following?topic=1');
  await waitFor(() => expect(researchApi.following).toHaveBeenCalledWith(0, expect.objectContaining({ topicIds: [1], topicOnly: false })));
  const bubble = await screen.findByRole('link', { name: 'Real-time video generation' });
  expect(bubble).toHaveAttribute('aria-current', 'true');
  expect(bubble).toHaveAttribute('href', '/following');
  expect(screen.getByRole('link', { name: 'Speculative decoding' })).toHaveAttribute('href', '/following?topic=1&topic=2');
  expect(screen.queryByText(/Showing only papers about/)).not.toBeInTheDocument();
});
it('still filters to every topic for older only=topic links', async () => {
  vi.mocked(researchApi.topics).mockResolvedValue([topic]);
  renderFeed('/following?only=topic');
  await waitFor(() => expect(researchApi.following).toHaveBeenCalledWith(0, expect.objectContaining({ topicOnly: true })));
  expect(await screen.findByText(/Showing only papers about your topics/)).toBeInTheDocument();
});
it('offers accounts without a topic the pop-up from Edit feed above their follows feed', async () => {
  renderFeed();
  fireEvent.click(await screen.findByRole('button', { name: 'Edit feed' }));
  expect(await screen.findByRole('textbox', { name: 'Research topic' })).toBeInTheDocument();
  expect(await screen.findByText('A paper')).toBeInTheDocument();
});
it('leaves the topic pop-up closed after the only topic is removed', async () => {
  vi.mocked(researchApi.follows).mockResolvedValue([]);
  vi.mocked(researchApi.topics).mockResolvedValue([topic]);
  vi.spyOn(researchApi, 'removeTopic').mockImplementation(async () => {
    vi.mocked(researchApi.topics).mockResolvedValue([]);
  });
  renderFeed();
  fireEvent.click(await screen.findByRole('button', { name: 'Edit feed' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Real-time video generation' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByRole('heading', { name: 'Build your personal research feed', hidden: true })).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(screen.getByRole('button', { name: 'Build your feed' })).toBeInTheDocument();
});
it('shows the feed for an account that follows only a topic', async () => {
  vi.mocked(researchApi.follows).mockResolvedValue([]);
  vi.mocked(researchApi.topics).mockResolvedValue([{ ...topic, status: 'running', judged: 200, total: 4700 }]);
  renderFeed();
  expect(await screen.findByText(/Showing the closest papers about \u201cReal-time video generation\u201d now/)).toBeInTheDocument();
  expect(await screen.findByText('A paper')).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Build your personal research feed' })).not.toBeInTheDocument();
});
it('has no separate trending (X) tab: X likes are part of the trending score', async () => {
  renderFeed('/');
  expect(await screen.findByRole('button', { name: 'trending' })).toHaveClass('active');
  expect(screen.queryByRole('button', { name: 'trending (X)' })).not.toBeInTheDocument();
});

it('keeps popular topics out of the bubble row and offers them in Edit feed', async () => {
  vi.mocked(researchApi.featuredTopics).mockResolvedValue([{ id: 23, text: 'OCR releases', label: null, followers: 5,
    creator: { username: 'nielsr', avatar_url: 'https://huggingface.co/api/users/nielsr/avatar?redirect=true' } }]);
  renderFeed();
  const row = await screen.findByRole('navigation', { name: 'Filter your feed' });
  await screen.findByText('A paper');
  expect(within(row).queryByText(/OCR releases/)).not.toBeInTheDocument();
  fireEvent.click(within(row).getByRole('button', { name: 'Edit feed' }));
  expect(await screen.findByRole('button', { name: /OCR releases/ })).toHaveTextContent('@nielsr');
  expect(screen.getByRole('link', { name: 'Open the OCR releases page' })).toHaveAttribute('href', '/topics/23-ocr-releases');
});

it('follows the popular topics a visitor picked before signing in', async () => {
  sessionStorage.setItem('pwc:following-pending-topic-follows', JSON.stringify([23]));
  const follow = vi.spyOn(researchApi, 'followTopic').mockResolvedValue({ ...topic, id: 23, text: 'OCR releases' });
  renderFeed();
  await waitFor(() => expect(follow).toHaveBeenCalledWith(23));
  await waitFor(() => expect(sessionStorage.getItem('pwc:following-pending-topic-follows')).toBeNull());
});

it('keeps popular topics a visitor picked when following them fails, and retries', async () => {
  sessionStorage.setItem('pwc:following-pending-topic-follows', JSON.stringify([23, 24]));
  const follow = vi.spyOn(researchApi, 'followTopic')
    .mockResolvedValueOnce({ ...topic, id: 23 }).mockRejectedValueOnce(new Error('down'))
    .mockResolvedValueOnce({ ...topic, id: 24 });
  renderFeed();
  fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));
  await waitFor(() => expect(sessionStorage.getItem('pwc:following-pending-topic-follows')).toBeNull());
  expect(follow).toHaveBeenLastCalledWith(24);
  expect(follow).toHaveBeenCalledTimes(3);
});

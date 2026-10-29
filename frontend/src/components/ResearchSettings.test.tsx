import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { researchApi } from '@/lib/api/research';
import ResearchSettings from './ResearchSettings';
import ResearchFollowButton from './ResearchFollowButton';

const auth = vi.hoisted(() => ({ user: { hf_subject: 'alice', username: 'alice' }, isLoading: false }));
vi.mock('@/lib/authContext', () => ({ useAuth: () => auth, useOptionalAuth: () => auth }));
function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return <QueryClientProvider client={client}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>;
}
beforeEach(() => { vi.spyOn(researchApi, 'topic').mockResolvedValue(null); });
afterEach(() => vi.restoreAllMocks());
describe('research topic', () => {
  const saved = { text: 'real-time video generation', label: null, set_at: '2026-10-28T10:00:00Z', status: 'pending' as const,
    judged: 0, total: null, suggestions: [] };
  it('saves a trimmed topic and reports backfill progress', async () => {
    vi.spyOn(researchApi, 'follows').mockResolvedValue([]);
    vi.spyOn(researchApi, 'email').mockResolvedValue({ enabled: false, email: null, suppressed: false, delivery_ready: true });
    const set = vi.spyOn(researchApi, 'setTopic').mockResolvedValue({ ...saved, status: 'running', judged: 200, total: 4700 });
    render(<ResearchSettings />, { wrapper });
    const input = await screen.findByRole('textbox', { name: 'Research topic' });
    expect(screen.getByRole('button', { name: 'Follow topic' })).toBeDisabled();
    fireEvent.change(input, { target: { value: '  real-time   video generation ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Follow topic' }));
    await waitFor(() => expect(set).toHaveBeenCalledWith('real-time video generation'));
    expect(await screen.findByText('Your feed shows the closest papers now. Refining matches: 200 of 4,700 checked…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Update topic' })).toBeDisabled();
  });
  it('removes the topic and names exact catalog matches', async () => {
    vi.mocked(researchApi.topic).mockResolvedValue({ ...saved, status: 'done', suggestions: [
      { kind: 'task', entity_id: 3, name: 'Video Generation', url: '/tasks/video-generation' },
    ] });
    vi.spyOn(researchApi, 'follows').mockResolvedValue([]);
    vi.spyOn(researchApi, 'email').mockResolvedValue({ enabled: false, email: null, suppressed: false, delivery_ready: true });
    const clear = vi.spyOn(researchApi, 'clearTopic').mockResolvedValue();
    render(<ResearchSettings />, { wrapper });
    expect(await screen.findByRole('link', { name: 'Video Generation' })).toHaveAttribute('href', '/tasks/video-generation');
    expect(screen.getByText(/new ones are added every hour/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(clear).toHaveBeenCalled());
    expect(await screen.findByRole('button', { name: 'Follow topic' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Research topic' })).toHaveValue('');
  });
  it('lets a failed topic be saved again unchanged to retry', async () => {
    vi.mocked(researchApi.topic).mockResolvedValue({ ...saved, status: 'failed' });
    vi.spyOn(researchApi, 'follows').mockResolvedValue([]);
    vi.spyOn(researchApi, 'email').mockResolvedValue({ enabled: false, email: null, suppressed: false, delivery_ready: true });
    const set = vi.spyOn(researchApi, 'setTopic').mockResolvedValue(saved);
    render(<ResearchSettings />, { wrapper });
    fireEvent.click(await screen.findByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(set).toHaveBeenCalledWith('real-time video generation'));
  });
});
describe('research follows', () => {
  it('shows the verified destination, disabled-delivery status, and explicit opt-in', async () => {
    vi.spyOn(researchApi, 'follows').mockResolvedValue([]);
    const preferences = { enabled: false, email: 'alice@example.com', suppressed: false, delivery_ready: false };
    vi.spyOn(researchApi, 'email').mockResolvedValue(preferences);
    const save = vi.spyOn(researchApi, 'setEmail').mockResolvedValue({ ...preferences, enabled: true });
    render(<ResearchSettings />, { wrapper });
    expect(await screen.findByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText(/Weekly emails have not launched yet/)).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('switch'));
    await waitFor(() => expect(save).toHaveBeenCalledWith(true, expect.anything()));
  });
  it('groups follows by kind and lets an unfollow be undone in place before refetching', async () => {
    const follow = { kind: 'method' as const, entity_id: 7, name: 'Mixture of Experts', url: '/methods/moe', created_at: '2026-10-03T10:00:00Z' };
    const list = vi.spyOn(researchApi, 'follows').mockResolvedValue([follow]);
    vi.spyOn(researchApi, 'email').mockResolvedValue({ enabled: false, email: null, suppressed: false, delivery_ready: true });
    const change = vi.spyOn(researchApi, 'setFollow').mockResolvedValue();
    render(<ResearchSettings />, { wrapper });
    expect(await screen.findByRole('heading', { name: 'Methods' })).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeDisabled();
    // Refetches never settle, so every state change must come from the mutation itself.
    list.mockReturnValue(new Promise(() => {}));
    fireEvent.click(screen.getByRole('button', { name: 'Unfollow Mixture of Experts' }));
    await waitFor(() => expect(change).toHaveBeenCalledWith('method', 7, false));
    expect(await screen.findByRole('button', { name: 'Follow Mixture of Experts' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Follow Mixture of Experts' }));
    await waitFor(() => expect(change).toHaveBeenCalledWith('method', 7, true));
    expect(await screen.findByRole('button', { name: 'Unfollow Mixture of Experts' })).toBeInTheDocument();
    expect(screen.queryByText(/not following anything/)).not.toBeInTheDocument();
  });
  it('blocks overlapping unfollows so an interest is listed once', async () => {
    const a = { kind: 'task' as const, entity_id: 1, name: 'Alpha', url: '/tasks/alpha', created_at: '2026-10-01T10:00:00Z' };
    const b = { kind: 'task' as const, entity_id: 2, name: 'Beta', url: '/tasks/beta', created_at: '2026-10-01T10:00:00Z' };
    const list = vi.spyOn(researchApi, 'follows').mockResolvedValue([a, b]);
    vi.spyOn(researchApi, 'email').mockResolvedValue({ enabled: false, email: null, suppressed: false, delivery_ready: true });
    let finish = () => {};
    const change = vi.spyOn(researchApi, 'setFollow').mockReturnValue(new Promise<void>(resolve => { finish = resolve; }));
    render(<ResearchSettings />, { wrapper });
    const unfollowAlpha = await screen.findByRole('button', { name: 'Unfollow Alpha' });
    list.mockReturnValue(new Promise(() => {}));
    fireEvent.click(unfollowAlpha);
    fireEvent.click(unfollowAlpha);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Unfollow Beta' })).toBeDisabled());
    finish();
    expect(await screen.findAllByRole('button', { name: 'Follow Alpha' })).toHaveLength(1);
    expect(change).toHaveBeenCalledWith('task', 1, false);
  });
  it('follows and unfollows with the stable entity id', async () => {
    const list = vi.spyOn(researchApi, 'follows').mockResolvedValue([]);
    const change = vi.spyOn(researchApi, 'setFollow').mockResolvedValue();
    render(<ResearchFollowButton kind="task" entityId="12" />, { wrapper });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Follow' })).toBeEnabled());
    list.mockResolvedValue([{ kind: 'task', entity_id: 12, name: 'Task', url: '/tasks/task', created_at: '' }]);
    fireEvent.click(screen.getByRole('button', { name: 'Follow' }));
    expect(await screen.findByRole('button', { name: 'Unfollow' })).toBeInTheDocument();
    expect(change).toHaveBeenCalledWith('task', '12', true);
    fireEvent.click(screen.getByRole('button', { name: 'Unfollow' }));
    await waitFor(() => expect(change).toHaveBeenCalledWith('task', '12', false));
  });
  it('explains following and links guests to Hugging Face sign-in', async () => {
    vi.spyOn(researchApi, 'follows').mockResolvedValue([]);
    render(<ResearchFollowButton kind="method" entityId="3" />, { wrapper });
    expect(await screen.findByText(/Get new papers using this method/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'your Following feed' })).toHaveAttribute('href', '/following');
    auth.user = null as unknown as typeof auth.user;
    try {
      render(<ResearchFollowButton kind="method" entityId="3" />, { wrapper });
      expect(screen.getByRole('link', { name: 'Follow' }).getAttribute('href')).toContain('/auth/hf/login');
      expect(screen.getByText('Sign in to get new papers using this method.')).toBeInTheDocument();
      vi.stubEnv('VITE_DISABLE_AUTH', '1');
      const { container } = render(<ResearchFollowButton kind="task" entityId="4" />, { wrapper });
      expect(container).toBeEmptyDOMElement();
    } finally {
      vi.unstubAllEnvs();
      auth.user = { hf_subject: 'alice', username: 'alice' };
    }
  });
  it('confirms a new follow only for the entity that was followed', async () => {
    const list = vi.spyOn(researchApi, 'follows').mockResolvedValue([]);
    vi.spyOn(researchApi, 'setFollow').mockResolvedValue();
    const { rerender } = render(<ResearchFollowButton kind="task" entityId="12" />, { wrapper });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Follow' })).toBeEnabled());
    list.mockResolvedValue([
      { kind: 'task', entity_id: 12, name: 'Task', url: '/tasks/task', created_at: '' },
      { kind: 'task', entity_id: 13, name: 'Other', url: '/tasks/other', created_at: '' },
    ]);
    fireEvent.click(screen.getByRole('button', { name: 'Follow' }));
    expect(await screen.findByText(/Added to/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Manage in Settings' })).toHaveAttribute('href', '/settings');
    rerender(<ResearchFollowButton kind="task" entityId="13" />);
    expect(screen.getByRole('button', { name: 'Unfollow' })).toBeInTheDocument();
    expect(screen.queryByText(/Added to/)).not.toBeInTheDocument();
  });
});

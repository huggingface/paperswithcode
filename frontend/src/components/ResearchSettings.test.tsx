import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { researchApi } from '@/lib/api/research';
import ResearchSettings from './ResearchSettings';
import ResearchFollowButton from './ResearchFollowButton';
import FollowingView from '@/views/FollowingView';

const auth = vi.hoisted(() => ({ user: { hf_subject: 'alice', username: 'alice' }, isLoading: false }));
vi.mock('@/lib/authContext', () => ({ useAuth: () => auth, useOptionalAuth: () => auth }));
function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return <QueryClientProvider client={client}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>;
}
afterEach(() => vi.restoreAllMocks());
describe('research follows', () => {
  it('shows the verified destination, disabled-delivery status, and explicit opt-in', async () => {
    vi.spyOn(researchApi, 'follows').mockResolvedValue([]);
    const preferences = { enabled: false, email: 'alice@example.com', suppressed: false, delivery_ready: false };
    vi.spyOn(researchApi, 'email').mockResolvedValue(preferences);
    const save = vi.spyOn(researchApi, 'setEmail').mockResolvedValue({ ...preferences, enabled: true });
    render(<ResearchSettings />, { wrapper });
    expect(await screen.findByText('Destination: alice@example.com')).toBeInTheDocument();
    expect(screen.getByText(/Email delivery is not available yet/)).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('switch'));
    await waitFor(() => expect(save).toHaveBeenCalledWith(true, expect.anything()));
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
  it('shows match reasons and benchmark scores on the bookmarkable feed', async () => {
    vi.spyOn(researchApi, 'following').mockResolvedValue([{ paper_key: 'a', title: 'A paper', url: '/paper/1',
      summary: 'Summary.', published: '2026-10-10', reasons: ['Task (subtask)', 'Benchmark'],
      scores: [{ benchmark: 'Benchmark', model: 'Model', metrics: { Accuracy: 91 } }] }]);
    render(<FollowingView />, { wrapper });
    expect(await screen.findByRole('link', { name: 'A paper' })).toHaveAttribute('href', '/paper/1');
    expect(screen.getByText(/Task \(subtask\)/)).toBeInTheDocument();
    expect(screen.getByText(/Accuracy: 91/)).toBeInTheDocument();
  });
});

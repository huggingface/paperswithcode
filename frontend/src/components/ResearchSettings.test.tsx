import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { researchApi } from '@/lib/api/research';
import ResearchSettings from './ResearchSettings';
import ResearchFollowButton from './ResearchFollowButton';

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
    expect(await screen.findByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText(/Weekly emails have not launched yet/)).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('switch'));
    await waitFor(() => expect(save).toHaveBeenCalledWith(true, expect.anything()));
  });
  it('groups follows by kind and lets an unfollow be undone in place', async () => {
    const follow = { kind: 'method' as const, entity_id: 7, name: 'Mixture of Experts', url: '/methods/moe', created_at: '2026-10-03T10:00:00Z' };
    const list = vi.spyOn(researchApi, 'follows').mockResolvedValue([follow]);
    vi.spyOn(researchApi, 'email').mockResolvedValue({ enabled: false, email: null, suppressed: false, delivery_ready: true });
    const change = vi.spyOn(researchApi, 'setFollow').mockResolvedValue();
    render(<ResearchSettings />, { wrapper });
    expect(await screen.findByRole('heading', { name: 'Methods' })).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeDisabled();
    list.mockResolvedValue([]);
    fireEvent.click(screen.getByRole('button', { name: 'Unfollow Mixture of Experts' }));
    await waitFor(() => expect(change).toHaveBeenCalledWith('method', 7, false));
    expect(await screen.findByRole('button', { name: 'Follow Mixture of Experts' })).toBeInTheDocument();
    list.mockResolvedValue([follow]);
    fireEvent.click(screen.getByRole('button', { name: 'Follow Mixture of Experts' }));
    await waitFor(() => expect(change).toHaveBeenCalledWith('method', 7, true));
    expect(await screen.findByRole('button', { name: 'Unfollow Mixture of Experts' })).toBeInTheDocument();
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
});

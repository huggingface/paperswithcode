import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { researchApi, type PublicTopic } from '@/lib/api/research';
import { ApiError } from '@/lib/apiTransport';
import TopicView from './TopicView';

const auth = vi.hoisted(() => ({ user: { hf_subject: 'bob', username: 'bob' } as { hf_subject: string; username: string } | null, isLoading: false }));
vi.mock('@/lib/authContext', () => ({ useAuth: () => auth, useOptionalAuth: () => auth }));
vi.mock('@/hooks/useIntersectionObserver', () => ({ useIntersectionObserver: () => ({ targetRef: () => {}, isIntersecting: false }) }));

const topic: PublicTopic = {
  id: 23, text: 'OCR releases', label: null, status: 'done', is_public: true, indexable: true,
  creator: { username: 'nielsr', avatar_url: 'https://huggingface.co/api/users/nielsr/avatar?redirect=true' },
  followers: 3, follower_avatars: [{ username: 'alice', avatar_url: 'https://huggingface.co/api/users/alice/avatar?redirect=true' }],
  following: false, is_creator: false,
};

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>
    <Routes><Route path="/topics/:topicParam" element={<TopicView />} /></Routes>
  </MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  auth.user = { hf_subject: 'bob', username: 'bob' };
  vi.spyOn(researchApi, 'topicPapers').mockResolvedValue([]);
  vi.spyOn(researchApi, 'topics').mockResolvedValue([]);
});
afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});

describe('TopicView', () => {
  it('shows the creator, followers, and follows the topic by id', async () => {
    const view = vi.spyOn(researchApi, 'publicTopic').mockResolvedValue(topic);
    const follow = vi.spyOn(researchApi, 'followTopic').mockImplementation(async () => {
      view.mockResolvedValue({ ...topic, following: true, followers: 4 });
      return { id: 23, text: 'OCR releases', label: null, set_at: null, status: 'done', judged: 0, total: null, suggestions: [], is_public: true, is_creator: false };
    });
    renderAt('/topics/23-ocr-releases');
    expect(await screen.findByRole('heading', { name: 'OCR releases' })).toBeInTheDocument();
    expect(view).toHaveBeenCalledWith(23);
    expect(screen.getByRole('link', { name: '@nielsr' })).toHaveAttribute('href', 'https://huggingface.co/nielsr');
    expect(screen.getByText('3 people follow this topic')).toBeInTheDocument();
    expect(screen.getByTitle('@alice')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Follow' }));
    await waitFor(() => expect(follow).toHaveBeenCalledWith(23));
    expect(await screen.findByText('4 people follow this topic')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Following/ })).toHaveAttribute('aria-pressed', 'true');
    // Unfollowing refreshes the header too.
    const remove = vi.spyOn(researchApi, 'removeTopic').mockImplementation(async () => {
      view.mockResolvedValue(topic);
    });
    fireEvent.click(screen.getByRole('button', { name: /Following/ }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith(23));
    expect(await screen.findByText('3 people follow this topic')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Follow' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('keeps thin topics out of search engines', async () => {
    vi.spyOn(researchApi, 'publicTopic').mockResolvedValue({ ...topic, indexable: false });
    renderAt('/topics/23');
    await screen.findByRole('heading', { name: 'OCR releases' });
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute('content', 'noindex, follow');
  });

  it('reports private or missing topics as not found', async () => {
    vi.spyOn(researchApi, 'publicTopic').mockRejectedValue(new ApiError(new Response(null, { status: 404, statusText: 'Not Found' }), ''));
    renderAt('/topics/99');
    expect(await screen.findByRole('heading', { name: 'Topic not found' })).toBeInTheDocument();
  });

  it('creates an edited copy as your own topic', async () => {
    vi.spyOn(researchApi, 'publicTopic').mockResolvedValue(topic);
    const add = vi.spyOn(researchApi, 'addTopic').mockResolvedValue({
      id: 60, text: 'OCR model releases', label: null, set_at: null, status: 'pending', judged: 0, total: null, suggestions: [], is_public: true, is_creator: true,
    });
    renderAt('/topics/23');
    fireEvent.click(await screen.findByRole('button', { name: 'Duplicate and edit' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Your topic' }), { target: { value: 'OCR model releases' } });
    fireEvent.click(screen.getByRole('button', { name: 'Follow topic' }));
    await waitFor(() => expect(add).toHaveBeenCalledWith('OCR model releases'));
  });
});

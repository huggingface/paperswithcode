import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { catalogApi } from '@/lib/api/catalog';
import MethodsIndexView from './MethodsIndexView';
import TagsIndexView from './TagsIndexView';

vi.mock('@/components/TaxonomySuggestionTile', () => ({ TaxonomySuggestionTile: () => null }));

const page = <T,>(results: T[]) => ({ count: results.length, results, next_page: null, previous_page: null });

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/tasks" element={<TagsIndexView />} /><Route path="/methods" element={<MethodsIndexView />} />
  </Routes></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  vi.spyOn(catalogApi, 'listAreas').mockResolvedValue(page([
    { id: '1', name: 'Vision' }, { id: '3', name: 'General' },
  ]));
  vi.spyOn(catalogApi, 'trendingTasks').mockResolvedValue({ recent_days: 30, baseline_days: 180, results: [
    { id: '7', name: 'World Models', slug: 'world-models', area_id: '3', recent_paper_count: 91,
      baseline_paper_count: 348, share_lift: 2.12, trend_score: 9.6 } as never,
  ] });
  vi.spyOn(catalogApi, 'trendingMethods').mockResolvedValue({ recent_days: 30, baseline_days: 180, results: [
    { id: '9', name: 'GRPO', slug: 'grpo', area_id: '3', recent_paper_count: 174,
      baseline_paper_count: 835, share_lift: 1.69, trend_score: 8.7 },
  ] });
  vi.spyOn(catalogApi, 'areasWithTasks').mockResolvedValue({ results: [
    { id: '1', name: 'Vision', tasks: [{ id: '2', name: 'Image Classification', slug: 'image-classification', paper_count: 5 }] },
  ] } as never);
  vi.spyOn(catalogApi, 'methodIndex').mockResolvedValue({ count: 1, results: [
    { id: '4', name: 'Dropout', slug: 'dropout', area_id: '1', paper_count: 3, trend_score: 0 },
  ] });
});
afterEach(() => { vi.restoreAllMocks(); });

it('shows trending tasks across areas above the full domain listing', async () => {
  const { container } = renderAt('/tasks');
  const link = await screen.findByRole('link', { name: /World Models/ });
  expect(link).toHaveAttribute('href', '/tasks/world-models');
  expect(link).toHaveTextContent('General');
  expect(link).toHaveTextContent('91 papers / 30d');
  expect(link).toHaveTextContent('2.1×');
  expect(catalogApi.trendingTasks).toHaveBeenCalledWith({ limit: 12, min_recent_papers: 10 });
  const allTask = await screen.findByRole('link', { name: /Image Classification/ });
  const trending = container.querySelector('#trending');
  expect(trending).toContainElement(link);
  expect(trending).not.toContainElement(allTask);
  expect(trending!.compareDocumentPosition(allTask) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

it('scrolls area links to their section once trending has rendered above it', async () => {
  let resolveTrending!: (value: Awaited<ReturnType<typeof catalogApi.trendingTasks>>) => void;
  vi.mocked(catalogApi.trendingTasks).mockReturnValue(new Promise((resolve) => { resolveTrending = resolve; }));
  const scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView;
  window.history.replaceState(null, '', '/tasks#area-vision');
  renderAt('/tasks#area-vision');
  expect(await screen.findByRole('link', { name: /Image Classification/ })).toBeInTheDocument();
  expect(scrollIntoView).not.toHaveBeenCalled();
  resolveTrending({ recent_days: 30, baseline_days: 180, results: [] });
  await waitFor(() => expect(scrollIntoView).toHaveBeenCalledWith({ block: 'start' }));
  expect(scrollIntoView.mock.contexts[0]).toHaveAttribute('id', 'area-vision');
  window.history.replaceState(null, '', '/');
});

it('shows trending methods above the full method listing', async () => {
  const { container } = renderAt('/methods');
  const link = await screen.findByRole('link', { name: /GRPO/ });
  expect(link).toHaveAttribute('href', '/methods/grpo');
  expect(link).toHaveTextContent('174 papers / 30d');
  expect(catalogApi.trendingMethods).toHaveBeenCalledWith({ limit: 12 });
  const allMethod = await screen.findByRole('link', { name: /Dropout/ });
  expect(container.querySelector('#trending')).not.toContainElement(allMethod);
});

it('hides the trending section when nothing is gaining momentum', async () => {
  vi.mocked(catalogApi.trendingMethods).mockResolvedValue({ recent_days: 30, baseline_days: 180, results: [] });
  const { container } = renderAt('/methods');
  expect(await screen.findByRole('link', { name: /Dropout/ })).toBeInTheDocument();
  expect(container.querySelector('#trending')).toBeNull();
});

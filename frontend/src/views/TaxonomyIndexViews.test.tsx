import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
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

it('opens the tasks directory on trending tasks across areas', async () => {
  renderAt('/tasks');
  const link = await screen.findByRole('link', { name: /World Models/ });
  expect(link).toHaveAttribute('href', '/tasks/world-models');
  expect(link).toHaveTextContent('General');
  expect(link).toHaveTextContent('91 papers / 30d');
  expect(link).toHaveTextContent('2.1×');
  expect(screen.getByRole('tab', { name: 'trending' })).toHaveAttribute('aria-selected', 'true');
  expect(catalogApi.trendingTasks).toHaveBeenCalledWith({ limit: 24, min_recent_papers: 10 });
  expect(catalogApi.areasWithTasks).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('tab', { name: 'all domains' }));
  expect(await screen.findByRole('link', { name: /Image Classification/ })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /World Models/ })).not.toBeInTheDocument();
});

it('opens the full listing for area anchors and ?view=all', async () => {
  renderAt('/tasks#area-vision');
  expect(await screen.findByRole('link', { name: /Image Classification/ })).toBeInTheDocument();
  expect(catalogApi.trendingTasks).not.toHaveBeenCalled();
});

it('opens the methods directory on trending methods', async () => {
  renderAt('/methods');
  const link = await screen.findByRole('link', { name: /GRPO/ });
  expect(link).toHaveAttribute('href', '/methods/grpo');
  expect(link).toHaveTextContent('174 papers / 30d');
  expect(catalogApi.methodIndex).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('tab', { name: 'all methods' }));
  expect(await screen.findByRole('link', { name: /Dropout/ })).toBeInTheDocument();
});

it('keeps ?view=all on the methods listing', async () => {
  renderAt('/methods?view=all');
  expect(await screen.findByRole('link', { name: /Dropout/ })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'all methods' })).toHaveAttribute('aria-selected', 'true');
  expect(catalogApi.trendingMethods).not.toHaveBeenCalled();
});

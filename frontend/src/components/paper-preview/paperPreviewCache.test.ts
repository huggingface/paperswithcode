import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import type { Paper } from '@/lib/api/papers.types';
import { createPaperPreviewCache, paperPreviewQueryKey } from './paperPreviewCache';

const paper = (overrides: Partial<Paper>): Paper => ({
  id: '1', arxiv_id: null, url_abs: null, url_pdf: null, title: 'Paper', abstract: '', authors: [],
  published: '2024-01-01', version: 'v1', is_latest_version: true, citation_count: 0, ...overrides,
});

describe('paper preview cache', () => {
  it('seeds preview cards for every matched entry and maps keys to route ids', async () => {
    const client = new QueryClient();
    const lookup = vi.fn().mockResolvedValue({ references: [
      { key: 'cite.gu2024', matched_by: 'title', paper: paper({ id: '13', arxiv_id: '2312.00752', title: 'Mamba' }) },
      { key: 'cite.blog', matched_by: 'title', paper: paper({ id: '9001', title: 'A blog post' }) },
      { key: 'cite.missing', matched_by: null, paper: null },
    ] });
    const cache = createPaperPreviewCache(client, { lookup });
    const matches = await cache.lookup([{ key: 'cite.gu2024', titles: ['Mamba'] }, { key: 'cite.blog' }, { key: 'cite.missing' }]);
    expect([...matches]).toEqual([['cite.gu2024', '2312.00752'], ['cite.blog', '9001']]);
    expect(client.getQueryData<Paper>(paperPreviewQueryKey('2312.00752v2'))?.title).toBe('Mamba');
    expect(client.getQueryData<Paper>(paperPreviewQueryKey('9001'))?.title).toBe('A blog post');
  });

  it('warms uncached arXiv ids once and splits large batches', async () => {
    const client = new QueryClient();
    client.setQueryData(paperPreviewQueryKey('1405.0312'), paper({ id: '2', arxiv_id: '1405.0312' }));
    const lookup = vi.fn().mockResolvedValue({ references: [] });
    const cache = createPaperPreviewCache(client, { lookup });
    cache.warm(['1405.0312', '2501.22222', '2501.22222v3']);
    cache.warm(['2501.22222']);
    await vi.waitFor(() => expect(lookup).toHaveBeenCalledTimes(1));
    expect(lookup).toHaveBeenCalledWith([{ key: '2501.22222', arxiv_id: '2501.22222' }]);
    const many = Array.from({ length: 250 }, (_, index) => ({ key: `cite.${index}`, arxiv_id: `2501.${String(index).padStart(5, '0')}` }));
    await cache.lookup(many);
    expect(lookup).toHaveBeenCalledTimes(3);
    expect(lookup.mock.calls[1][0]).toHaveLength(200);
    expect(lookup.mock.calls[2][0]).toHaveLength(50);
  });

  it('swallows warm-up failures so hovering can still fetch on demand', async () => {
    const client = new QueryClient();
    const lookup = vi.fn().mockRejectedValue(new Error('offline'));
    createPaperPreviewCache(client, { lookup }).warm(['2501.22222']);
    await vi.waitFor(() => expect(lookup).toHaveBeenCalled());
    expect(client.getQueryData(paperPreviewQueryKey('2501.22222'))).toBeUndefined();
  });
});

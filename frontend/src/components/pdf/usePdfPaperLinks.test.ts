import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { usePdfPaperLinks } from './usePdfPaperLinks';

afterEach(() => document.querySelectorAll('[data-pdf-test]').forEach(node => node.remove()));
function annotation() {
  const section = document.createElement('section');
  section.className = 'linkAnnotation';
  section.dataset.annotationId = '1R';
  const anchor = document.createElement('a');
  anchor.href = 'https://arxiv.org/abs/1405.0312';
  section.append(anchor);
  return { section, anchor };
}

describe('PDF annotation lifecycle', () => {
  it('enhances asynchronously appended links and rebinds after a zoom render', async () => {
    const root = document.createElement('div');
    root.dataset.pdfTest = 'true';
    document.body.append(root);
    const ref = { current: root };
    const resolve = vi.fn().mockResolvedValue('1405.0312');
    const { result } = renderHook(() => usePdfPaperLinks(ref, true, resolve));
    act(() => result.current.onAnnotations([{ id: '1R', url: 'https://arxiv.org/abs/1405.0312' }]));
    const first = annotation();
    act(() => root.append(first.section));
    await waitFor(() => expect(result.current.paperLinks[0]?.anchor).toBe(first.anchor));
    const second = annotation();
    act(() => root.replaceChildren(second.section));
    await waitFor(() => expect(result.current.paperLinks[0]?.anchor).toBe(second.anchor));
  });

  it('discards results for annotation nodes that disappeared while resolving', async () => {
    const root = document.createElement('div');
    root.dataset.pdfTest = 'true';
    document.body.append(root);
    const first = annotation();
    root.append(first.section);
    let finish!: (id: string) => void;
    const resolve = vi.fn(() => new Promise<string>(r => { finish = r; }));
    const ref = { current: root };
    const { result } = renderHook(() => usePdfPaperLinks(ref, true, resolve));
    act(() => result.current.onAnnotations([{ id: '1R', dest: 'cite.lin' }]));
    await waitFor(() => expect(resolve).toHaveBeenCalled());
    act(() => first.section.remove());
    await act(async () => { finish('1405.0312'); });
    expect(result.current.paperLinks).toEqual([]);
  });
});

import { describe, expect, it, vi } from 'vitest';
import type { PDFDocumentProxy } from 'pdfjs-dist/types/src/display/api';
import { arxivIdFromUrl, createPdfCitationResolver, referenceTitleCandidates } from './pdfCitationLinks';

describe('arXiv PDF links', () => {
  it.each([
    ['https://arxiv.org/abs/2501.12345v2', '2501.12345'],
    ['http://www.arxiv.org/pdf/1706.03762.pdf#page=2', '1706.03762'],
    ['https://arxiv.org/html/2501.12345v3', '2501.12345'],
    ['https://arxiv.org/abs/hep-th/9901001v2', 'hep-th/9901001'],
    ['https://arxiv.org.evil.test/abs/2501.12345', null],
    ['https://evil.test/arxiv.org/abs/2501.12345', null],
    ['javascript:alert(1)', null],
    ['https://arxiv.org/search/?query=2501.12345', null],
  ])('recognizes only paper URLs: %s', (url, id) => expect(arxivIdFromUrl(url)).toBe(id));

  const destination = (x: number, y: number) => [11, { name: 'XYZ' }, x, y, null];
  function document(ambiguous = false) {
    const getAnnotations = vi.fn().mockResolvedValue([
      { url: 'https://arxiv.org/abs/1405.0312', rect: [85, 610, 150, 620] },
      { url: 'https://arxiv.org/abs/2501.22222', rect: [85, 460, 150, 470] },
      { url: 'https://arxiv.org/abs/2501.33333', rect: [320, 610, 400, 620] },
      ...(ambiguous ? [{ url: 'https://arxiv.org/abs/2501.44444', rect: [85, 600, 150, 610] }] : []),
    ]);
    const getDestinations = vi.fn().mockResolvedValue({
      'cite.lin2014': destination(83, 650),
      'cite.next': destination(83, 500),
      'cite.right': destination(315, 650),
      'section.2': destination(83, 700),
    });
    const getPage = vi.fn().mockResolvedValue({ getAnnotations, getTextContent: vi.fn().mockResolvedValue({ items: [] }) });
    return { pdf: { getDestinations, getPage } as unknown as PDFDocumentProxy, getPage, getDestinations };
  }

  it('maps an author/year destination to its own entry in a two-column bibliography', async () => {
    const { pdf, getPage, getDestinations } = document();
    const resolve = createPdfCitationResolver(pdf);
    expect(await resolve({ id: '1', dest: 'cite.lin2014' })).toBe('1405.0312');
    expect(await resolve({ id: '2', dest: 'cite.next' })).toBe('2501.22222');
    expect(await resolve({ id: '3', dest: 'cite.right' })).toBe('2501.33333');
    expect(await resolve({ id: '4', dest: 'cite.lin2014' })).toBe('1405.0312');
    expect(getDestinations).toHaveBeenCalledTimes(1);
    expect(getPage).toHaveBeenCalledTimes(2);
    expect(getPage).toHaveBeenCalledWith(12);
  });

  it('leaves ambiguous references, unknown destinations, and section links unchanged', async () => {
    const { pdf } = document(true);
    const resolve = createPdfCitationResolver(pdf);
    expect(await resolve({ id: '1', dest: 'cite.lin2014' })).toBeNull();
    expect(await resolve({ id: '2', dest: 'cite.missing' })).toBeNull();
    expect(await resolve({ id: '3', dest: 'section.2' })).toBeNull();
  });

  it('recognizes direct links without scanning destinations', async () => {
    const { pdf, getDestinations } = document();
    expect(await createPdfCitationResolver(pdf)({ id: '1', url: 'https://arxiv.org/pdf/2501.12345' })).toBe('2501.12345');
    expect(getDestinations).not.toHaveBeenCalled();
  });

  it('recognizes explicit unlinked arXiv identifiers split across text items', async () => {
    const { pdf, getPage } = document();
    const text = (str: string, y: number) => ({ str, transform: [10, 0, 0, 10, 85, y] });
    getPage.mockResolvedValue({
      getAnnotations: async () => [],
      getTextContent: async () => ({ items: [text('arXiv:', 610), text('1405.', 610), text('0312v2', 610), text('arXiv:2501.22222', 460)] }),
    });
    expect(await createPdfCitationResolver(pdf)({ id: '1', dest: 'cite.lin2014' })).toBe('1405.0312');
  });
});

describe('bibliography title candidates', () => {
  it('splits a numbered entry into author, title, and venue sentences', () => {
    expect(referenceTitleCandidates('[13] Albert Gu and Tri Dao. Mamba: Linear-time sequence mod- eling with selective state spaces. In Conference on Language Modeling (COLM), 2024.')).toEqual([
      'Mamba: Linear-time sequence mod- eling with selective state spaces',
      'In Conference on Language Modeling (COLM), 2024',
      'Albert Gu and Tri Dao',
      'Mamba: Linear-time sequence mod- eling with selective state spaces. In Conference on Language Modeling (COLM), 2024',
      'Albert Gu and Tri Dao. Mamba: Linear-time sequence mod- eling with selective state spaces',
    ]);
  });

  it('keeps identifiers and decimals intact, drops URLs and arXiv preprint venues, and caps the list', () => {
    const candidates = referenceTitleCandidates('A. B. Cee, D. E. Eff, and G. Aitch. Llama 2.5 vs. GPT-4: A study. arXiv preprint arXiv:2312.17238, 2023. URL https://arxiv.org/abs/2312.17238.');
    expect(candidates).toContain('Llama 2.5 vs. GPT-4: A study');
    expect(candidates.some(candidate => /https?:/.test(candidate) || /^arXiv preprint/.test(candidate))).toBe(false);
    expect(referenceTitleCandidates(Array.from({ length: 12 }, (_, index) => `Sentence number ${index} here`).join('. ')).length).toBe(8);
  });
});

describe('catalog title lookup', () => {
  const destination = (x: number, y: number) => [11, { name: 'XYZ' }, x, y, null];
  const text = (str: string, y: number) => ({ str, hasEOL: true, transform: [10, 0, 0, 10, 85, y] });
  function document() {
    const getPage = vi.fn().mockResolvedValue({
      getAnnotations: async () => [{ url: 'https://arxiv.org/abs/2501.22222', rect: [85, 460, 150, 470] }],
      getTextContent: async () => ({ items: [
        text('Tsung-Yi Lin, Michael Maire, et al.', 640),
        text('Microsoft COCO: Common objects in', 625),
        text('context. In ECCV, 2014.', 610),
        text('Someone Else. Another paper. arXiv preprint', 470),
      ] }),
    });
    const getDestinations = vi.fn().mockResolvedValue({ 'cite.lin2014': destination(83, 650), 'cite.next': destination(83, 500) });
    return { pdf: { getDestinations, getPage } as unknown as PDFDocumentProxy, getPage };
  }

  it('sends every entry to the catalog on creation and resolves title-only citations from the answer', async () => {
    const lookup = vi.fn().mockResolvedValue(new Map([['cite.lin2014', '1405.0312']]));
    const { pdf, getPage } = document();
    const resolve = createPdfCitationResolver(pdf, lookup);
    expect(await resolve({ id: '1', dest: 'cite.lin2014' })).toBe('1405.0312');
    expect(await resolve({ id: '2', dest: 'cite.next' })).toBe('2501.22222');
    expect(lookup).toHaveBeenCalledTimes(1);
    expect(lookup).toHaveBeenCalledWith([
      { key: 'cite.lin2014', arxiv_id: null, titles: expect.arrayContaining(['Microsoft COCO: Common objects in context']) },
      { key: 'cite.next', arxiv_id: '2501.22222', titles: expect.arrayContaining(['Someone Else. Another paper']) },
    ]);
    expect(getPage).toHaveBeenCalledTimes(2);
  });

  it('falls back to explicit identifiers when the catalog is unreachable', async () => {
    const { pdf } = document();
    const resolve = createPdfCitationResolver(pdf, vi.fn().mockRejectedValue(new Error('offline')));
    expect(await resolve({ id: '1', dest: 'cite.lin2014' })).toBeNull();
    expect(await resolve({ id: '2', dest: 'cite.next' })).toBe('2501.22222');
  });

  it('never contacts the catalog without a lookup', async () => {
    const { pdf, getPage } = document();
    createPdfCitationResolver(pdf);
    await Promise.resolve();
    expect(getPage).not.toHaveBeenCalled();
  });
});

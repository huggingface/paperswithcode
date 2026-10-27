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
    const getPage = vi.fn().mockResolvedValue({ view: [0, 0, 600, 800], getAnnotations, getTextContent: vi.fn().mockResolvedValue({ items: [] }) });
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
      view: [0, 0, 600, 800],
      getAnnotations: async () => [],
      getTextContent: async () => ({ items: [text('arXiv:', 610), text('1405.', 610), text('0312v2', 610), text('arXiv:2501.22222', 460)] }),
    });
    expect(await createPdfCitationResolver(pdf)({ id: '1', dest: 'cite.lin2014' })).toBe('1405.0312');
  });

  it('places resolved bibliography entries on their page, without the footer below the last one', async () => {
    const { pdf, getPage } = document();
    const text = (str: string, x: number, y: number) => ({ str, transform: [10, 0, 0, 10, x, y], width: 200, height: 10 });
    getPage.mockResolvedValue({
      view: [0, 0, 600, 800],
      getAnnotations: async () => [],
      getTextContent: async () => ({ items: [
        text('[1] T. Lin. Microsoft COCO.', 85, 640), text('arXiv:1405.0312', 85, 628),
        text('[2] Unresolved entry without identifiers.', 85, 490),
        text('[3] Right column. arXiv:2501.33333', 320, 640),
        text('15', 300, 40),
      ] }),
    });
    const lookup = vi.fn().mockResolvedValue(new Map());
    const resolve = createPdfCitationResolver(pdf, lookup);
    expect(await resolve.bibliographyLinks(12)).toEqual([
      { name: 'cite.lin2014', routeId: '1405.0312', box: [142, 188, 475, 218] },
      { name: 'cite.right', routeId: '2501.33333', box: [533, 188, 867, 203] },
    ]);
    expect(await resolve.bibliographyLinks(3)).toEqual([]);
  });
});

describe('PDFs without bibliography destinations', () => {
  const item = (str: string, x: number, y: number, hasEOL = false) => ({ str, transform: [8, 0, 0, 8, x, y], width: 100, height: 8, hasEOL });
  function wordExport() {
    const pages: Record<number, unknown[]> = {
      1: [item('Prior work [7] shows this.', 47, 600, true), item('References', 47, 500, true)],
      2: [
        item('', 47, 700, true), item('[', 47, 700), item('1]', 50, 700), item(' A. Author. A first paper.', 60, 700, true),
        item('arXiv:2501.11111', 57, 691, true),
        item('[2] B. Author. A second paper. arXiv:2501.22222', 47, 682, true),
        item('See also [9] in the text.', 57, 673, true),
        item('[3] C. Author. A third paper.', 313, 700, true),
      ],
    };
    const getPage = vi.fn(async (page: number) => ({
      view: [0, 0, 600, 800],
      getAnnotations: async () => [],
      getTextContent: async () => ({ items: pages[page] }),
    }));
    return { numPages: 2, getDestinations: vi.fn().mockResolvedValue({}), getPage } as unknown as PDFDocumentProxy;
  }

  it('finds numbered entries after the References heading, including split labels', async () => {
    const lookup = vi.fn().mockResolvedValue(new Map([['text:3', '2501.33333']]));
    const resolve = createPdfCitationResolver(wordExport(), lookup);
    const links = await resolve.bibliographyLinks(2);
    expect(links.map(({ name, routeId }) => [name, routeId])).toEqual([
      ['text:1', '2501.11111'],
      ['text:2', '2501.22222'],
      ['text:3', '2501.33333'],
    ]);
    expect(await resolve.bibliographyLinks(1)).toEqual([]);
    expect(lookup.mock.calls[0][0].map((query: { key: string }) => query.key)).toEqual(['text:1', 'text:2', 'text:3']);
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
      view: [0, 0, 600, 800],
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

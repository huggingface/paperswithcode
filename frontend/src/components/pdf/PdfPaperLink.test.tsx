import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PdfBibliographyEntryLink, PdfPaperLink } from './PdfPaperLink';

const get = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api/papers', () => ({ papersApi: { get } }));

afterEach(() => { document.querySelectorAll('[data-pdf-test]').forEach(node => node.remove()); get.mockReset(); });
function setup(internal: boolean, onShowReference?: (dest: string) => Promise<boolean>) {
  const section = document.createElement('section');
  section.dataset.pdfTest = 'true';
  const anchor = document.createElement('a');
  anchor.href = internal ? '#' : 'https://arxiv.org/abs/1405.0312';
  const navigate = vi.fn((event: MouseEvent) => event.preventDefault());
  anchor.addEventListener('click', navigate);
  section.append(anchor);
  document.body.append(section);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><MemoryRouter>
    <PdfPaperLink anchor={anchor} routeId="1405.0312" internal={internal} dest="cite.lin2014" onShowReference={onShowReference} />
  </MemoryRouter></QueryClientProvider>);
  return { ...view, anchor, navigate };
}

describe('PDF paper previews', () => {
  it('loads the shared card on hover and preserves the original citation navigation', async () => {
    get.mockResolvedValue({ title: 'Microsoft COCO', authors: ['Tsung-Yi Lin'], arxiv_id: '1405.0312', tasks: [] });
    const { anchor, navigate, unmount } = setup(true);
    expect(anchor.style.display).toBe('none');
    expect(get).not.toHaveBeenCalled();
    const trigger = screen.getByRole('link', { name: 'Citation 1405.0312' });
    await userEvent.hover(trigger);
    expect(await screen.findByText('Microsoft COCO')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('1405.0312', false);
    expect(screen.getByRole('link', { name: 'Open paper ↗' })).toHaveAttribute('target', '_blank');
    const card = screen.getByText('Microsoft COCO').closest('a');
    expect(card).toHaveAttribute('href', '/paper/1405.0312');
    expect(card).toHaveAttribute('target', '_blank');
    fireEvent.click(screen.getByRole('button', { name: 'Jump to reference' }));
    expect(navigate).toHaveBeenCalledTimes(1);
    fireEvent.click(trigger);
    expect(navigate).toHaveBeenCalledTimes(2);
    unmount();
    expect(anchor.style.display).toBe('');
  });

  it('jumps to and flashes the bibliography entry, following the PDF link when its box is unknown', async () => {
    get.mockResolvedValue({ title: 'Microsoft COCO', authors: ['Tsung-Yi Lin'], arxiv_id: '1405.0312', tasks: [] });
    const onShowReference = vi.fn().mockResolvedValueOnce(true).mockResolvedValueOnce(false);
    const { navigate } = setup(true, onShowReference);
    const trigger = screen.getByRole('link', { name: 'Citation 1405.0312' });
    await userEvent.hover(trigger);
    fireEvent.click(await screen.findByRole('button', { name: 'Jump to reference' }));
    await waitFor(() => expect(onShowReference).toHaveBeenCalledWith('cite.lin2014'));
    expect(navigate).not.toHaveBeenCalled();
    fireEvent.click(trigger);
    await waitFor(() => expect(navigate).toHaveBeenCalledTimes(1));
    expect(onShowReference).toHaveBeenCalledTimes(2);
  });

  it('keeps external URLs usable when the catalog has no preview', async () => {
    get.mockRejectedValue(new Error('Not found'));
    setup(false);
    const trigger = screen.getByRole('link', { name: 'arXiv paper 1405.0312' });
    expect(trigger).toHaveAttribute('href', 'https://arxiv.org/abs/1405.0312');
    expect(trigger).toHaveAttribute('target', '_blank');
    await userEvent.hover(trigger);
    await waitFor(() => expect(screen.getByText('Preview unavailable')).toBeInTheDocument());
    expect(screen.queryByRole('link', { name: 'Open paper ↗' })).not.toBeInTheDocument();
  });

  it('hands every place the text cites an entry to the viewer', async () => {
    get.mockResolvedValue({ title: 'Microsoft COCO', authors: ['Tsung-Yi Lin'], arxiv_id: '1405.0312', tasks: [] });
    const citations = [[{ page: 2, bbox: [10, 20, 30, 40] }], [{ page: 5, bbox: [50, 60, 70, 80] }, { page: 5, bbox: [5, 82, 20, 95] }]];
    const onShowCitations = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter>
      <PdfBibliographyEntryLink name="cite.lin2014" routeId="1405.0312" box={[100, 100, 400, 140]} citations={citations} onShowCitations={onShowCitations} />
    </MemoryRouter></QueryClientProvider>);
    await userEvent.hover(screen.getByRole('link', { name: 'Reference 1405.0312' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Jump to citations (2)' }));
    expect(onShowCitations).toHaveBeenCalledWith(citations);
  });

  it('offers no jump for an entry the text never cites', async () => {
    get.mockResolvedValue({ title: 'Microsoft COCO', authors: ['Tsung-Yi Lin'], arxiv_id: '1405.0312', tasks: [] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter>
      <PdfBibliographyEntryLink name="cite.lin2014" routeId="1405.0312" box={[100, 100, 400, 140]} citations={[]} onShowCitations={vi.fn()} />
    </MemoryRouter></QueryClientProvider>);
    await userEvent.hover(screen.getByRole('link', { name: 'Reference 1405.0312' }));
    expect(await screen.findByRole('link', { name: 'Open paper ↗' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Jump to citation/ })).not.toBeInTheDocument();
  });
});

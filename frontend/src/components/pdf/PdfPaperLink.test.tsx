import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PdfPaperLink } from './PdfPaperLink';

const get = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api/papers', () => ({ papersApi: { get } }));

afterEach(() => { document.querySelectorAll('[data-pdf-test]').forEach(node => node.remove()); get.mockReset(); });
function setup(internal: boolean) {
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
    <PdfPaperLink anchor={anchor} routeId="1405.0312" internal={internal} />
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
    fireEvent.click(screen.getByRole('button', { name: 'Jump to reference' }));
    expect(navigate).toHaveBeenCalledTimes(1);
    fireEvent.click(trigger);
    expect(navigate).toHaveBeenCalledTimes(2);
    unmount();
    expect(anchor.style.display).toBe('');
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
});

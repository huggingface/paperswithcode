import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SortableList from './SortableList';

const items = ['alpha', 'beta', 'gamma'];

function renderList(onReorder = vi.fn()) {
  const list = () => <SortableList items={items} itemKey={item => item} itemLabel={item => item} onReorder={onReorder}
    renderItem={(item, handle) => <div>{handle}<span>{item}</span></div>} />;
  const { rerender } = render(list());
  // Rows are 20px tall and laid out in DOM order, so moving a row moves its offsetTop.
  screen.getAllByRole('listitem').forEach(row => {
    Object.defineProperty(row, 'offsetTop', { get: () => Array.from(row.parentElement!.children).indexOf(row) * 20 });
    Object.defineProperty(row, 'offsetHeight', { get: () => 20 });
  });
  // Record those layout positions, as a browser would have on the first render.
  rerender(list());
  return onReorder;
}

describe('SortableList', () => {
  it('drags a row by its handle and reports the new order once', () => {
    const onReorder = renderList();
    const handle = screen.getByRole('button', { name: /^Reorder alpha/ });
    fireEvent.pointerDown(handle, { button: 0, pointerId: 1, clientY: 10 });
    fireEvent.pointerMove(window, { pointerId: 1, clientY: 55 });
    expect(screen.getAllByRole('listitem').map(row => row.textContent)).toEqual(['beta', 'gamma', 'alpha']);
    expect(onReorder).not.toHaveBeenCalled();
    fireEvent.pointerUp(window, { pointerId: 1, clientY: 55 });
    expect(onReorder).toHaveBeenCalledWith(['beta', 'gamma', 'alpha']);
  });

  it('cancels a drag without reordering', () => {
    const onReorder = renderList();
    const handle = screen.getByRole('button', { name: /^Reorder alpha/ });
    fireEvent.pointerDown(handle, { button: 0, pointerId: 1, clientY: 10 });
    fireEvent.pointerMove(window, { pointerId: 1, clientY: 55 });
    fireEvent.pointerCancel(window, { pointerId: 1 });
    expect(onReorder).not.toHaveBeenCalled();
    expect(screen.getAllByRole('listitem').map(row => row.textContent)).toEqual(items);
  });

  it('moves a row with the arrow keys and stops at the ends', () => {
    const onReorder = renderList();
    fireEvent.keyDown(screen.getByRole('button', { name: /^Reorder beta/ }), { key: 'ArrowDown' });
    expect(onReorder).toHaveBeenLastCalledWith(['alpha', 'gamma', 'beta']);
    fireEvent.keyDown(screen.getByRole('button', { name: /^Reorder alpha/ }), { key: 'ArrowUp' });
    expect(onReorder).toHaveBeenCalledTimes(1);
  });

  it('slides moved rows from their old slot and keeps the dragged row under the pointer', () => {
    renderList();
    fireEvent.pointerDown(screen.getByRole('button', { name: /^Reorder alpha/ }), { button: 0, pointerId: 1, clientY: 10 });
    fireEvent.pointerMove(window, { pointerId: 1, clientY: 35 });
    const [beta, alpha] = screen.getAllByRole('listitem');
    // Alpha now sits in slot 1 (top 20) but the pointer moved 25px, so it is drawn 5px lower.
    expect(alpha.textContent).toBe('alpha');
    expect(alpha.style.transform).toBe('translateY(5px)');
    // Beta moved up one slot and slides from where it was.
    expect(beta.style.transition).toContain('transform');
    expect(beta.style.transform).toBe('');
    fireEvent.pointerUp(window, { pointerId: 1 });
    expect(alpha.style.transform).toBe('');
    expect(alpha.style.transition).toContain('transform');
  });

  it('skips the slide when the user prefers reduced motion', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduce') }));
    renderList();
    fireEvent.keyDown(screen.getByRole('button', { name: /^Reorder beta/ }), { key: 'ArrowUp' });
    expect(screen.getAllByRole('listitem').every(row => row.style.transition === '')).toBe(true);
    vi.unstubAllGlobals();
  });

  it('keeps the dropped row lifted until it has glided into its slot', () => {
    vi.useFakeTimers();
    renderList();
    fireEvent.pointerDown(screen.getByRole('button', { name: /^Reorder alpha/ }), { button: 0, pointerId: 1, clientY: 10 });
    fireEvent.pointerMove(window, { pointerId: 1, clientY: 35 });
    fireEvent.pointerUp(window, { pointerId: 1 });
    const alpha = screen.getAllByRole('listitem').find(row => row.textContent === 'alpha')!;
    expect(alpha).toHaveClass('is-dragging');
    expect(alpha.style.transition).toContain('box-shadow');
    act(() => { vi.advanceTimersByTime(200); });
    expect(alpha).not.toHaveClass('is-dragging');
    vi.useRealTimers();
  });

  it('starts a slide from where a row is drawn, including a slide in flight', () => {
    renderList();
    const beta = screen.getAllByRole('listitem')[1];
    const handle = screen.getByRole('button', { name: /^Reorder beta/ });
    // Beta is still drawn 12px below its slot when it moves up a slot (20px).
    const real = window.getComputedStyle.bind(window);
    vi.spyOn(window, 'getComputedStyle').mockImplementation((element, pseudo) =>
      element === beta ? ({ transform: 'matrix(1, 0, 0, 1, 0, 12)' } as CSSStyleDeclaration) : real(element, pseudo));
    const seen: string[] = [];
    Object.defineProperty(beta.style, 'transform', {
      configurable: true,
      get: () => seen[seen.length - 1] ?? '',
      set: (value: string) => { seen.push(value); },
    });
    fireEvent.keyDown(handle, { key: 'ArrowUp' });
    // Old slot 20 + 12px in flight - new slot 0 = starts 32px down, then slides to rest.
    expect(seen).toEqual(['translateY(32px)', '']);
    vi.restoreAllMocks();
  });
});

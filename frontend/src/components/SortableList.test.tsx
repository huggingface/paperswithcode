import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SortableList from './SortableList';

const items = ['alpha', 'beta', 'gamma'];

function renderList(onReorder = vi.fn()) {
  render(<SortableList items={items} itemKey={item => item} itemLabel={item => item} onReorder={onReorder}
    renderItem={(item, handle) => <div>{handle}<span>{item}</span></div>} />);
  // Rows are 20px tall, stacked from the top of the viewport.
  screen.getAllByRole('listitem').forEach((row, index) => {
    row.getBoundingClientRect = () => ({ top: index * 20, height: 20, bottom: index * 20 + 20, left: 0, right: 100, width: 100, x: 0, y: index * 20, toJSON: () => ({}) });
  });
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
});

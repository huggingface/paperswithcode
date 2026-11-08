import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { GripVertical } from 'lucide-react';

type Key = string | number;

/** Drag a row by its handle (mouse or touch) or move it with the arrow keys; rows reorder live while dragging. */
export default function SortableList<T>({ items, itemKey, itemLabel, onReorder, renderItem, className, disabled = false }: {
  items: T[];
  itemKey: (item: T) => Key;
  /** Names the row in the handle's accessible label. */
  itemLabel: (item: T) => string;
  /** Called once per finished drag or key press with the new order. */
  onReorder: (items: T[]) => void;
  /** Renders a row; place `handle` where the grip should appear. */
  renderItem: (item: T, handle: ReactNode, dragging: boolean) => ReactNode;
  className?: string;
  disabled?: boolean;
}) {
  const [drag, setDrag] = useState<{ key: Key; order: T[] } | null>(null);
  // A dropped order shows until the parent passes new items, so the row never jumps back while saving.
  const [settled, setSettled] = useState<{ from: T[]; order: T[] } | null>(null);
  const rows = useRef(new Map<Key, HTMLElement>());
  const list = drag?.order ?? (settled?.from === items ? settled.order : items);
  const sameOrder = (a: T[], b: T[]) => a.length === b.length && a.every((item, i) => itemKey(item) === itemKey(b[i]));

  // Follow the pointer on window: a moving row's DOM node is re-inserted, which would drop pointer capture.
  const latest = useRef({ items, onReorder, drag });
  latest.current = { items, onReorder, drag };
  const dragging = drag !== null;
  useEffect(() => {
    if (!dragging) return;
    const onMove = (event: PointerEvent) => {
      const y = event.clientY;
      setDrag(current => {
        if (!current) return current;
        const dragged = current.order.find(item => itemKey(item) === current.key)!;
        const others = current.order.filter(item => itemKey(item) !== current.key);
        // The dragged row goes after every other row whose middle is above the pointer.
        const index = others.filter(item => {
          const rect = rows.current.get(itemKey(item))?.getBoundingClientRect();
          return rect ? rect.top + rect.height / 2 < y : false;
        }).length;
        const order = [...others.slice(0, index), dragged, ...others.slice(index)];
        return sameOrder(order, current.order) ? current : { ...current, order };
      });
    };
    const finish = (commit: boolean) => {
      const { drag: current, items: saved, onReorder: report } = latest.current;
      if (commit && current && !sameOrder(current.order, saved)) {
        setSettled({ from: saved, order: current.order });
        report(current.order);
      }
      setDrag(null);
    };
    const onUp = () => finish(true);
    const onCancel = () => finish(false);
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onCancel);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onCancel);
    };
    // itemKey and sameOrder are pure; the listeners live for one drag.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dragging]);
  const moveBy = (key: Key, step: number) => {
    const from = items.findIndex(item => itemKey(item) === key);
    const to = from + step;
    if (to < 0 || to >= items.length) return;
    const order = [...items];
    order.splice(to, 0, ...order.splice(from, 1));
    setSettled({ from: items, order });
    onReorder(order);
  };

  return <ul className={['sortable-list', className].filter(Boolean).join(' ')}>
    {list.map(item => {
      const key = itemKey(item);
      const isDragged = drag?.key === key;
      const handle = <button type="button" className="sortable-handle" disabled={disabled || items.length < 2}
        aria-label={`Reorder ${itemLabel(item)}. Use the up and down arrow keys to move it.`}
        onPointerDown={event => {
          if (event.button !== 0) return;
          event.preventDefault();
          setDrag({ key, order: items });
        }}
        onKeyDown={(event: KeyboardEvent<HTMLButtonElement>) => {
          if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
          event.preventDefault();
          moveBy(key, event.key === 'ArrowUp' ? -1 : 1);
        }}>
        <GripVertical aria-hidden="true" />
      </button>;
      return <li key={key} className={isDragged ? 'sortable-item is-dragging' : 'sortable-item'}
        ref={element => { if (element) rows.current.set(key, element); else rows.current.delete(key); }}>
        {renderItem(item, handle, isDragged)}
      </li>;
    })}
  </ul>;
}

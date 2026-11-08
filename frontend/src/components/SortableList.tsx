import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { GripVertical } from 'lucide-react';

type Key = string | number;

const DURATION = 180;
const MOVE = `transform ${DURATION}ms cubic-bezier(0.2, 0, 0, 1), box-shadow ${DURATION}ms ease`;
const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

/** The vertical offset a row is drawn at right now, including a slide still in flight. */
function currentShift(row: HTMLElement): number {
  const values = getComputedStyle(row).transform.match(/matrix(3d)?\(([^)]+)\)/);
  if (!values) return 0;
  const numbers = values[2].split(',').map(Number);
  return (values[1] ? numbers[13] : numbers[5]) || 0;
}

/** Drag a row by its handle (mouse or touch) or move it with the arrow keys. The dragged row follows the
 * pointer and the others slide into their new places. */
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
  // The row that was just dropped keeps its lift (z-index, shadow) while it glides into its slot.
  const [dropped, setDropped] = useState<Key | null>(null);
  // A dropped order shows until the parent passes new items, so the row never jumps back while saving.
  const [settled, setSettled] = useState<{ from: T[]; order: T[] } | null>(null);
  const rows = useRef(new Map<Key, HTMLElement>());
  // Each row's layout position (offsetTop ignores transforms) after the last render.
  const tops = useRef(new Map<Key, number>());
  // Pointer y and where in the dragged row it grabbed, so the row stays under the pointer.
  const pointer = useRef({ y: 0, grab: 0 });
  const list = drag?.order ?? (settled?.from === items ? settled.order : items);
  const sameOrder = (a: T[], b: T[]) => a.length === b.length && a.every((item, i) => itemKey(item) === itemKey(b[i]));

  const followPointer = (row: HTMLElement) => {
    row.style.transition = 'none';
    row.style.transform = `translateY(${pointer.current.y - pointer.current.grab - row.offsetTop}px)`;
  };

  // FLIP: a row whose slot changed starts where it is drawn now (its old slot plus any slide in flight)
  // and slides to its new slot.
  useLayoutEffect(() => {
    const animate = !reducedMotion();
    rows.current.forEach((row, key) => {
      const top = row.offsetTop;
      const previous = tops.current.get(key);
      tops.current.set(key, top);
      if (key === drag?.key) return followPointer(row);
      if (!animate || previous === undefined || previous === top) return;
      const from = previous + currentShift(row) - top;
      row.style.transition = 'none';
      row.style.transform = `translateY(${from}px)`;
      void row.offsetHeight; // Apply the start position before transitioning from it.
      row.style.transition = MOVE;
      row.style.transform = '';
    });
  });

  // Follow the pointer on window: a moving row's DOM node is re-inserted, which would drop pointer capture.
  const latest = useRef({ items, onReorder, drag });
  latest.current = { items, onReorder, drag };
  const dragging = drag !== null;
  useEffect(() => {
    if (!dragging) return;
    const onMove = (event: PointerEvent) => {
      const y = event.clientY;
      pointer.current.y = y;
      const key = latest.current.drag?.key;
      const row = key === undefined ? undefined : rows.current.get(key);
      if (row) followPointer(row);
      // Compare layout positions (not on-screen ones, which shift while rows slide):
      // the dragged row goes after every other row whose middle is above its own middle.
      const middle = y - pointer.current.grab + (row?.offsetHeight ?? 0) / 2;
      setDrag(current => {
        if (!current) return current;
        const dragged = current.order.find(item => itemKey(item) === current.key)!;
        const others = current.order.filter(item => itemKey(item) !== current.key);
        const index = others.filter(item => {
          const other = rows.current.get(itemKey(item));
          return other ? other.offsetTop + other.offsetHeight / 2 < middle : false;
        }).length;
        const order = [...others.slice(0, index), dragged, ...others.slice(index)];
        return sameOrder(order, current.order) ? current : { ...current, order };
      });
    };
    const finish = (commit: boolean) => {
      const { drag: current, items: saved, onReorder: report } = latest.current;
      const row = current ? rows.current.get(current.key) : undefined;
      if (row && current) {
        // Glide the dropped row from under the pointer into its slot, still lifted.
        const animate = !reducedMotion();
        row.style.transition = animate ? MOVE : 'none';
        row.style.transform = '';
        if (animate) {
          setDropped(current.key);
          window.setTimeout(() => setDropped(key => (key === current.key ? null : key)), DURATION);
        }
      }
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
      const lifted = isDragged || dropped === key;
      const handle = <button type="button" className="sortable-handle" disabled={disabled || items.length < 2}
        aria-label={`Reorder ${itemLabel(item)}. Use the up and down arrow keys to move it.`}
        onPointerDown={event => {
          if (event.button !== 0) return;
          event.preventDefault();
          const row = rows.current.get(key);
          pointer.current = { y: event.clientY, grab: event.clientY - (row?.offsetTop ?? 0) };
          setDrag({ key, order: items });
        }}
        onKeyDown={(event: KeyboardEvent<HTMLButtonElement>) => {
          if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
          event.preventDefault();
          moveBy(key, event.key === 'ArrowUp' ? -1 : 1);
        }}>
        <GripVertical aria-hidden="true" />
      </button>;
      return <li key={key} className={lifted ? 'sortable-item is-dragging' : 'sortable-item'}
        ref={element => { if (element) rows.current.set(key, element); else rows.current.delete(key); }}>
        {renderItem(item, handle, isDragged)}
      </li>;
    })}
  </ul>;
}

import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';
import { cx } from './cx';

export interface TabItem<K extends string> {
  key: K;
  label: ReactNode;
  /** Small count after the label */
  count?: number;
}

interface TabsProps<K extends string> {
  items: TabItem<K>[];
  value: K;
  onChange: (key: K) => void;
  label: string;
}

/** Underlined tabs. Arrow keys move between them (WAI-ARIA tabs pattern). */
export function Tabs<K extends string>({ items, value, onChange, label }: TabsProps<K>) {
  const id = useId();
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const onKey = (e: KeyboardEvent, index: number) => {
    const delta = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!delta) return;
    e.preventDefault();
    const next = (index + delta + items.length) % items.length;
    refs.current[next]?.focus();
    onChange(items[next].key);
  };

  return (
    <div role="tablist" aria-label={label} className="flex gap-6 overflow-x-auto border-b border-line">
      {items.map((item, i) => {
        const selected = item.key === value;
        return (
          <button
            key={item.key}
            ref={(el) => (refs.current[i] = el)}
            id={`${id}-${item.key}`}
            role="tab"
            type="button"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.key)}
            onKeyDown={(e) => onKey(e, i)}
            className={cx(
              '-mb-px flex h-10 shrink-0 items-center gap-1.5 border-b-2 text-body transition-colors',
              selected ? 'border-accent font-medium text-ink' : 'border-transparent text-muted hover:text-ink',
            )}
          >
            {item.label}
            {item.count !== undefined && <span className="font-mono text-meta tabular text-muted">{item.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

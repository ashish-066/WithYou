import { useEffect, useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { Button } from './Button';
import { cx } from './cx';

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

/**
 * Shared behaviour for Dialog and Drawer: rendered in a portal inside the current
 * area (so it gets the area's colours), Escape closes, focus moves in and is kept
 * there, page behind doesn't scroll, focus returns to where it was on close.
 */
function useOverlay(open: boolean, onClose: () => void) {
  const panel = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const node = panel.current;
    const first = node?.querySelector<HTMLElement>('[data-autofocus]') ?? node?.querySelector<HTMLElement>(FOCUSABLE);
    // Deferred: when the overlay opens with the page (e.g. /app/invites?new=1), focus
    // set during the first render is taken back by the browser as the page finishes loading.
    const frame = window.setTimeout(() => (first ?? node)?.focus(), 0);

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        closeRef.current();
      } else if (e.key === 'Tab' && node) {
        const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE));
        if (items.length === 0) return;
        const [head, tail] = [items[0], items[items.length - 1]];
        if (e.shiftKey && document.activeElement === head) {
          e.preventDefault();
          tail.focus();
        } else if (!e.shiftKey && document.activeElement === tail) {
          e.preventDefault();
          head.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.clearTimeout(frame);
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
      previous?.focus?.();
    };
  }, [open]);

  return panel;
}

/** Portal target: the nearest area root, so overlays use that area's palette. */
function portalTarget(): HTMLElement {
  return (document.querySelector('[data-area]') as HTMLElement | null) ?? document.body;
}

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children?: ReactNode;
  /** Buttons, right-aligned. The safe choice goes first. */
  actions: ReactNode;
}

/** A question that needs an answer before going on (replaces window.confirm). */
export function Dialog({ open, onClose, title, children, actions }: DialogProps) {
  const panel = useOverlay(open, onClose);
  const titleId = useId();
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="relative w-full max-w-md border border-line bg-surface p-6"
      >
        <h2 id={titleId} className="font-display text-h3 text-ink">
          {title}
        </h2>
        {children && <div className="mt-2 text-body text-muted">{children}</div>}
        <div className="mt-6 flex justify-end gap-2">{actions}</div>
      </div>
    </div>,
    portalTarget(),
  );
}

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  /** Sticky footer, usually Cancel + the primary action */
  footer?: ReactNode;
  width?: 'md' | 'lg';
}

/** Side panel for create/edit forms, so the list stays in view. */
export function Drawer({ open, onClose, title, description, children, footer, width = 'md' }: DrawerProps) {
  const panel = useOverlay(open, onClose);
  const titleId = useId();
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cx(
          'relative flex h-full w-full flex-col border-l border-line bg-canvas',
          width === 'lg' ? 'max-w-2xl' : 'max-w-md',
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
          <div>
            <h2 id={titleId} className="font-display text-h3 text-ink">
              {title}
            </h2>
            {description && <p className="mt-1 text-meta text-muted">{description}</p>}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            aria-label="Close"
            icon={<X className="h-4 w-4" aria-hidden />}
          />
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-6 py-4">{footer}</div>}
      </div>
    </div>,
    portalTarget(),
  );
}

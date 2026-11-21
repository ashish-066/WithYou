/**
 * Notebook building blocks: the bits that make the app feel drawn by a person.
 *   SpeechBubble  what the buddy says (hand-drawn outline, tail toward the buddy)
 *   StickyNote    turmeric note with tape (next time, reminders)
 *   Scribble      a pencil underline under a heading
 *   MarginNote    small handwritten aside
 *   SketchButton  a big drawn button
 */
import type { ReactNode } from 'react';
import { ArrowRight } from 'lucide-react';

import { cx } from '@/ui/cx';

export function SpeechBubble({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx('relative', className)}>
      <div className="sketch relative bg-surface px-4 py-3 text-lead text-ink">{children}</div>
      {/* tail, pointing down-left at the buddy */}
      <svg aria-hidden width="28" height="20" viewBox="0 0 28 20" className="absolute -bottom-[17px] left-8">
        <path d="M2 1 C6 8 4 14 1 19 C9 15 16 9 20 1" style={{ fill: 'rgb(var(--c-surface))' }} />
        <path
          d="M2 1 C6 8 4 14 1 19 C9 15 16 9 20 1"
          style={{ fill: 'none', stroke: 'rgb(var(--c-ink) / 0.82)', strokeWidth: 2, strokeLinejoin: 'round' }}
        />
      </svg>
    </div>
  );
}

export function StickyNote({
  children,
  tilt = -1.5,
  className,
}: {
  children: ReactNode;
  tilt?: number;
  className?: string;
}) {
  return (
    <div className={cx('sticky tape relative rounded-[3px] px-5 pb-5 pt-6', className)} style={{ transform: `rotate(${tilt}deg)` }}>
      {children}
    </div>
  );
}

/** A pencil underline (wobbly, slightly off), sized to its text. */
export function Scribble({ children, color = 'turmeric', className }: { children: ReactNode; color?: 'turmeric' | 'terracotta' | 'accent'; className?: string }) {
  return (
    <span className={cx('relative inline-block', className)}>
      <span className="relative z-10">{children}</span>
      <svg
        aria-hidden
        viewBox="0 0 200 12"
        preserveAspectRatio="none"
        className="absolute -bottom-1 left-0 z-0 h-3 w-full"
      >
        <path
          d="M2 8 C40 3 70 10 105 6 C140 2 170 9 198 5"
          style={{ fill: 'none', stroke: `rgb(var(--c-${color}))`, strokeWidth: 5, strokeLinecap: 'round', opacity: 0.85 }}
        />
      </svg>
    </span>
  );
}

export function MarginNote({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cx('font-hand text-lead text-terracotta', className)}>{children}</p>;
}

export function SketchButton({
  children,
  onClick,
  tone = 'ink',
  className,
  type = 'button',
  disabled,
}: {
  children: ReactNode;
  onClick?: () => void;
  tone?: 'ink' | 'green' | 'paper';
  className?: string;
  type?: 'button' | 'submit';
  disabled?: boolean;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={cx(
        'sketch inline-flex min-h-12 items-center justify-center gap-2 px-6 text-lead font-semibold transition-transform active:translate-y-0.5 disabled:opacity-50',
        tone === 'ink' && 'bg-ink text-canvas',
        tone === 'green' && 'bg-accent text-accent-on',
        tone === 'paper' && 'bg-surface text-ink',
        className,
      )}
    >
      {children}
      <ArrowRight size={18} aria-hidden />
    </button>
  );
}

import { cx } from './cx';

export type Tone = 'neutral' | 'good' | 'warn' | 'bad' | 'live' | 'info';

/*
 * Status is always a word. The mark beside it differs by shape as well as colour,
 * so it reads without colour vision:
 *   good  filled circle    warn  filled diamond    bad  filled square
 *   live  ring (pulses)    info  ring              neutral  open square
 */
const toneText: Record<Tone, string> = {
  neutral: 'text-muted',
  good: 'text-good',
  warn: 'text-warn',
  bad: 'text-bad',
  live: 'text-accent',
  info: 'text-ink',
};

function Mark({ tone }: { tone: Tone }) {
  const common = 'inline-block shrink-0';
  switch (tone) {
    case 'good':
      return <span className={cx(common, 'h-2 w-2 rounded-full bg-current')} />;
    case 'warn':
      return <span className={cx(common, 'h-[7px] w-[7px] rotate-45 bg-current')} />;
    case 'bad':
      return <span className={cx(common, 'h-2 w-2 bg-current')} />;
    case 'live':
      return (
        <span className={cx(common, 'relative h-2.5 w-2.5')}>
          <span className="absolute inset-0 animate-ping rounded-full border border-current opacity-60" />
          <span className="absolute inset-0 rounded-full border-2 border-current" />
        </span>
      );
    case 'info':
      return <span className={cx(common, 'h-2.5 w-2.5 rounded-full border-2 border-current')} />;
    default:
      return <span className={cx(common, 'h-2 w-2 border border-current')} />;
  }
}

interface StatusLabelProps {
  tone?: Tone;
  children: React.ReactNode;
  className?: string;
}

export function StatusLabel({ tone = 'neutral', children, className }: StatusLabelProps) {
  return (
    <span className={cx('inline-flex items-center gap-1.5 text-meta font-medium', toneText[tone], className)}>
      <Mark tone={tone} />
      <span>{children}</span>
    </span>
  );
}

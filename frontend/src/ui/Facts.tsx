import { useState, type ReactNode } from 'react';
import { Check, Copy } from 'lucide-react';
import { Button } from './Button';
import { cx } from './cx';

/** Label/value pairs for side columns ("Started", "Ended", "Sent by"). */
export function DefinitionList({
  items,
  className,
}: {
  items: Array<{ term: string; value: ReactNode }>;
  className?: string;
}) {
  return (
    <dl className={cx('divide-y divide-line border-y border-line', className)}>
      {items.map((it) => (
        <div key={it.term} className="flex items-baseline justify-between gap-4 py-2.5">
          <dt className="shrink-0 text-meta text-muted">{it.term}</dt>
          <dd className="min-w-0 text-right text-body text-ink">{it.value ?? <span className="text-muted">—</span>}</dd>
        </div>
      ))}
    </dl>
  );
}

/** A value to copy: an invite link, a one-time password. */
export function CopyField({ value, label, mask }: { value: string; label: string; mask?: boolean }) {
  const [copied, setCopied] = useState(false);
  const [shown, setShown] = useState(!mask);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="flex items-stretch gap-2">
      <input
        readOnly
        aria-label={label}
        value={shown ? value : '•'.repeat(Math.min(value.length, 24))}
        onFocus={(e) => e.currentTarget.select()}
        className="h-9 min-w-0 flex-1 rounded-ui border border-line-strong bg-sunken px-3 font-mono text-meta text-ink"
      />
      {mask && (
        <Button size="md" variant="ghost" onClick={() => setShown((s) => !s)}>
          {shown ? 'Hide' : 'Show'}
        </Button>
      )}
      <Button
        onClick={copy}
        icon={copied ? <Check className="h-4 w-4" aria-hidden /> : <Copy className="h-4 w-4" aria-hidden />}
      >
        {copied ? 'Copied' : 'Copy'}
      </Button>
    </div>
  );
}

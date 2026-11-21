import type { ReactNode } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { Button } from './Button';

/** Nothing here yet: say what this place is for and offer the next step. */
export function EmptyState({ title, body, action }: { title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="border border-dashed border-line-strong px-6 py-12 text-center">
      <p className="font-display text-h3 text-ink">{title}</p>
      {body && <p className="mx-auto mt-2 max-w-md text-body text-muted">{body}</p>}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}

/** Something failed: say what, and offer a retry when it makes sense. */
export function ErrorState({
  title = 'This didn’t load',
  error,
  onRetry,
}: {
  title?: string;
  error?: unknown;
  onRetry?: () => void;
}) {
  const message = error instanceof Error ? error.message : typeof error === 'string' ? error : null;
  return (
    <div role="alert" className="flex items-start gap-3 border border-bad/40 bg-bad/5 px-4 py-3">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-bad" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-body font-medium text-ink">{title}</p>
        {message && <p className="mt-0.5 text-meta text-muted">{message}</p>}
      </div>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-meta text-muted" role="status">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label}
    </span>
  );
}

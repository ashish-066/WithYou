/** Display formats, in the viewer's own time zone. */

const dateTime = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});

const dateOnly = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' });

function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "13 Nov, 16:45" */
export function formatDateTime(iso: string | null | undefined): string {
  const d = parse(iso);
  return d ? dateTime.format(d) : '—';
}

/** "13 Nov 2026" */
export function formatDate(iso: string | null | undefined): string {
  const d = parse(iso);
  return d ? dateOnly.format(d) : '—';
}

/** "in 2 days", "3 hours ago" */
export function formatRelative(iso: string | null | undefined, now = Date.now()): string {
  const d = parse(iso);
  if (!d) return '—';
  const seconds = Math.round((d.getTime() - now) / 1000);
  const abs = Math.abs(seconds);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
  if (abs < 60) return rtf.format(seconds, 'second');
  if (abs < 3600) return rtf.format(Math.round(seconds / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(seconds / 3600), 'hour');
  return rtf.format(Math.round(seconds / 86400), 'day');
}

export function minutesSince(iso: string | null | undefined, now = Date.now()): number | null {
  const d = parse(iso);
  return d ? (now - d.getTime()) / 60_000 : null;
}

/** 0.86 → "86%" */
export function percent(value: number | null | undefined): string {
  return value == null ? '—' : `${Math.round(value * 100)}%`;
}


import { Link } from 'react-router-dom';
import { formatRelative } from '@/lib/format';
import type { PlatformWorker } from '@/types';
import { DataTable, EmptyState, ErrorState, PageHeader, StatusLabel, type Column, type Tone } from '@/ui';
import { usePlatformWorkers } from '../shared/data';

function stateOf(w: PlatformWorker): { word: string; tone: Tone } {
  if (w.stale) return { word: 'No heartbeat', tone: 'bad' };
  if (w.status === 'busy' || w.status === 'slow_task') return { word: 'Busy', tone: 'live' };
  if (w.status === 'idle' || w.status === 'active') return { word: 'Idle', tone: 'good' };
  return { word: w.status, tone: 'neutral' };
}

const ms = (v: number | null) => (v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`);

export function WorkersPage() {
  const workers = usePlatformWorkers();

  const columns: Column<PlatformWorker>[] = [
    {
      key: 'id',
      header: 'Worker',
      sortValue: (w) => w.worker_id,
      render: (w) => (
        <div className="min-w-0">
          <div className="truncate font-mono text-meta text-ink">{w.worker_id}</div>
          {w.hostname && <div className="truncate text-meta text-muted">{w.hostname}</div>}
        </div>
      ),
    },
    {
      key: 'state',
      header: 'State',
      sortValue: (w) => stateOf(w).word,
      render: (w) => <StatusLabel tone={stateOf(w).tone}>{stateOf(w).word}</StatusLabel>,
    },
    {
      key: 'session',
      header: 'Current interview',
      hideBelow: 'md',
      render: (w) =>
        w.current_session ? (
          <Link
            to={`/platform/interviews/${encodeURIComponent(w.current_session)}`}
            className="font-mono text-meta text-accent underline-offset-2 hover:underline"
          >
            {w.current_session}
          </Link>
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    {
      key: 'processed',
      header: 'Messages',
      numeric: true,
      align: 'right',
      sortValue: (w) => w.messages_processed,
      render: (w) => (
        <span>
          {w.messages_processed}
          {w.messages_failed > 0 && <span className="text-bad"> ({w.messages_failed} failed)</span>}
        </span>
      ),
    },
    { key: 'avg', header: 'Average', numeric: true, align: 'right', sortValue: (w) => w.avg_latency_ms, render: (w) => ms(w.avg_latency_ms), hideBelow: 'sm' },
    { key: 'p95', header: 'p95', numeric: true, align: 'right', sortValue: (w) => w.p95_latency_ms, render: (w) => ms(w.p95_latency_ms), hideBelow: 'lg' },
    {
      key: 'heartbeat',
      header: 'Last heartbeat',
      sortValue: (w) => w.last_heartbeat,
      render: (w) => formatRelative(w.last_heartbeat),
      hideBelow: 'md',
    },
  ];

  return (
    <>
      <PageHeader title="Workers" description="Brain workers processing interview messages. Updates every 5 seconds." />
      {workers.error ? (
        <ErrorState title="Workers didn’t load" error={workers.error} onRetry={() => workers.refetch()} />
      ) : (
        <DataTable
          caption="Workers"
          columns={columns}
          rows={workers.data ?? []}
          rowKey={(w) => w.worker_id}
          loading={workers.isLoading}
          empty={
            <EmptyState
              title="No workers running"
              body="Interviews can’t progress without a brain worker. Check the worker service on the host."
            />
          }
        />
      )}
    </>
  );
}

import { useState } from 'react';
import type { DeadLetter, PlatformStream } from '@/types';
import {
  Button,
  DataTable,
  DefinitionList,
  Drawer,
  EmptyState,
  ErrorState,
  PageHeader,
  Section,
  StatusLabel,
  type Column,
} from '@/ui';
import { usePlatformQueues } from '../shared/data';

/** Stream ids are "<milliseconds>-<sequence>" */
function idTime(id: string | null): string {
  const ms = Number(id?.split('-')[0]);
  return Number.isFinite(ms) && ms > 0 ? new Date(ms).toLocaleString() : '—';
}

function pretty(value: string | undefined): string {
  if (!value) return '';
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

export function QueuesPage() {
  const queues = usePlatformQueues();
  const [open, setOpen] = useState<DeadLetter | null>(null);

  const streamColumns: Column<PlatformStream>[] = [
    {
      key: 'name',
      header: 'Stream',
      render: (s) => (
        <div>
          <div className="font-medium text-ink">{s.kind === 'requests' ? 'To workers' : 'To the voice agent'}</div>
          <div className="font-mono text-[12px] text-muted">{s.name}</div>
        </div>
      ),
    },
    {
      key: 'pending',
      header: 'Waiting',
      numeric: true,
      align: 'right',
      render: (s) => <span className={s.pending_messages > 20 ? 'text-warn' : undefined}>{s.pending_messages}</span>,
    },
    { key: 'length', header: 'Kept', numeric: true, align: 'right', render: (s) => s.length, hideBelow: 'sm' },
    { key: 'groups', header: 'Consumer groups', numeric: true, align: 'right', render: (s) => s.consumer_groups, hideBelow: 'md' },
    { key: 'last', header: 'Newest message', render: (s) => idTime(s.last_entry_id), hideBelow: 'md' },
  ];

  const deadColumns: Column<DeadLetter>[] = [
    { key: 'at', header: 'When', numeric: true, render: (d) => idTime(d.id) },
    {
      key: 'session',
      header: 'Interview',
      render: (d) => <span className="font-mono text-meta">{d.session_id || '—'}</span>,
      hideBelow: 'sm',
    },
    { key: 'type', header: 'Message', render: (d) => d.message_type || d.type || '—', hideBelow: 'md' },
    { key: 'error', header: 'Error', render: (d) => <span className="line-clamp-2 text-muted">{d.error || d.reason || '—'}</span> },
    {
      key: 'view',
      header: <span className="sr-only">View</span>,
      align: 'right',
      render: (d) => (
        <Button size="sm" variant="ghost" onClick={() => setOpen(d)}>
          View
        </Button>
      ),
    },
  ];

  if (queues.error) {
    return (
      <>
        <PageHeader title="Queues" />
        <ErrorState title="Queues didn’t load" error={queues.error} onRetry={() => queues.refetch()} />
      </>
    );
  }

  const total = queues.data?.dead_letters_total ?? 0;

  return (
    <>
      <PageHeader
        title="Queues"
        description="Messages between the voice agent and the brain workers, and the ones that failed for good. Updates every 5 seconds."
      />

      <Section title="Streams">
        <DataTable
          caption="Message streams"
          columns={streamColumns}
          rows={queues.data?.streams ?? []}
          rowKey={(s) => s.name}
          loading={queues.isLoading}
        />
      </Section>

      <Section
        title="Dead letters"
        description="Messages a worker gave up on after repeated failures. Each is an interview event that didn’t take effect."
        actions={total > 0 ? <StatusLabel tone="warn">{`${total} in total`}</StatusLabel> : undefined}
      >
        <DataTable
          caption="Dead letters"
          columns={deadColumns}
          rows={queues.data?.dead_letters ?? []}
          rowKey={(d) => d.id}
          loading={queues.isLoading}
          pageSize={25}
          empty={<EmptyState title="No dead letters" body="Every message so far was processed." />}
        />
      </Section>

      <Drawer open={!!open} onClose={() => setOpen(null)} title="Dead letter" description={open?.id} width="lg">
        {open && (
          <>
            <DefinitionList
              items={Object.entries(open)
                .filter(([k]) => k !== 'payload' && k !== 'id')
                .map(([k, v]) => ({ term: k, value: <span className="break-all font-mono text-meta">{v}</span> }))}
            />
            {open.payload && (
              <>
                <h3 className="mb-2 mt-6 text-meta font-medium text-muted">Payload</h3>
                <pre className="overflow-auto border border-line bg-sunken p-4 font-mono text-meta text-ink">
                  {pretty(open.payload)}
                </pre>
              </>
            )}
          </>
        )}
      </Drawer>
    </>
  );
}

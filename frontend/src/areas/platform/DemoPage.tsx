import { useState } from 'react';
import type { DemoRunConfig, DemoRunStatus } from '@/types';
import {
  Button,
  Checkbox,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  Section,
  Spinner,
  StatusLabel,
  useToast,
  type Column,
  type Tone,
} from '@/ui';
import { useAuthConfig, useDemoControl, useDemoStatus } from '../shared/data';
import { NotFoundContent } from '../shared/routing';

type DemoSessionRow = DemoRunStatus['sessions'][number];

const STATUS: Record<string, { word: string; tone: Tone }> = {
  pending: { word: 'Waiting', tone: 'neutral' },
  active: { word: 'Running', tone: 'live' },
  completed: { word: 'Done', tone: 'good' },
};

/** Scripted load demo. Exists only where the server enables it (never on deployed servers). */
export function DemoPage() {
  const config = useAuthConfig();
  const enabled = !!config.data?.demo_enabled;
  const status = useDemoStatus(enabled);
  const control = useDemoControl();
  const toast = useToast();
  const [form, setForm] = useState<DemoRunConfig>({
    session_count: 10,
    max_workers: 10,
    response_delay_ms: 2000,
    auto_spawn_workers: true,
  });

  if (config.isLoading) return <Spinner />;
  if (!enabled) return <NotFoundContent />;

  const running = !!status.data?.running;
  const run = (v: Parameters<typeof control.mutate>[0]) =>
    control.mutate(v, { onError: (e) => toast.show(e instanceof Error ? e.message : 'That didn’t work', 'bad') });

  const columns: Column<DemoSessionRow>[] = [
    { key: 'name', header: 'Scripted candidate', render: (s) => s.candidate_name },
    {
      key: 'status',
      header: 'Status',
      render: (s) => <StatusLabel tone={STATUS[s.status]?.tone ?? 'neutral'}>{STATUS[s.status]?.word ?? s.status}</StatusLabel>,
    },
    { key: 'turns', header: 'Turns', numeric: true, align: 'right', render: (s) => s.turn_count },
    {
      key: 'rating',
      header: 'Rating',
      numeric: true,
      align: 'right',
      hideBelow: 'sm',
      render: (s) => (s.elo_rating == null ? '—' : Math.round(s.elo_rating)),
    },
    { key: 'rank', header: 'Rank', numeric: true, align: 'right', hideBelow: 'sm', render: (s) => s.elo_rank ?? '—' },
  ];

  const number = (k: keyof DemoRunConfig) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: Number(e.target.value) }));

  return (
    <>
      <PageHeader
        title="Demo"
        description="Starts scripted interviews to show how workers share the load. Each scripted turn makes real model calls."
        meta={
          status.data && (
            <StatusLabel tone={running ? 'live' : 'neutral'}>
              {running
                ? `Running, ${status.data.completed_sessions} of ${status.data.sessions.length} done`
                : 'Not running'}
            </StatusLabel>
          )
        }
      />

      <Section title="Run">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Interviews" className="w-full sm:w-32">
            {(f) => (
              <Input id={f.id} type="number" min={1} max={50} disabled={running} value={form.session_count} onChange={number('session_count')} />
            )}
          </Field>
          <Field label="Most workers" className="w-full sm:w-32">
            {(f) => (
              <Input id={f.id} type="number" min={1} max={20} disabled={running} value={form.max_workers} onChange={number('max_workers')} />
            )}
          </Field>
          <Field label="Delay between turns (ms)" className="w-full sm:w-48">
            {(f) => (
              <Input
                id={f.id}
                type="number"
                min={500}
                max={10000}
                step={500}
                disabled={running}
                value={form.response_delay_ms}
                onChange={number('response_delay_ms')}
              />
            )}
          </Field>
          <Checkbox
            className="pb-2"
            label="Start extra workers as needed"
            disabled={running}
            checked={form.auto_spawn_workers}
            onChange={(e) => setForm((f) => ({ ...f, auto_spawn_workers: e.target.checked }))}
          />
          {running ? (
            <Button variant="danger" loading={control.isPending} onClick={() => run({ action: 'stop' })}>
              Stop
            </Button>
          ) : (
            <Button variant="primary" loading={control.isPending} onClick={() => run({ action: 'start', config: form })}>
              Start demo
            </Button>
          )}
        </div>
        <p className="mt-3 text-meta text-muted">Watch workers and queues on the Workers and Health pages while it runs.</p>
      </Section>

      <Section title="Scripted interviews">
        {status.error ? (
          <ErrorState title="Demo status didn’t load" error={status.error} onRetry={() => status.refetch()} />
        ) : (
          <DataTable
            caption="Scripted interviews"
            columns={columns}
            rows={status.data?.sessions ?? []}
            rowKey={(s) => s.session_id}
            loading={status.isLoading}
            empty={<EmptyState title="Nothing started" body="Start the demo to run scripted interviews." />}
          />
        )}
      </Section>
    </>
  );
}

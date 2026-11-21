import { formatRelative } from '@/lib/format';
import type { HealthState, PlatformHealth } from '@/types';
import { DataTable, EmptyState, ErrorState, PageHeader, Section, StatusLabel, type Column, type Tone } from '@/ui';
import { usePlatformHealth, useSessions } from '../shared/data';
import { InterviewsTable, rowsFromSessions } from '../shared/InterviewsTable';

type Part = PlatformHealth['parts'][number];

export const HEALTH_TONE: Record<HealthState, { word: string; tone: Tone }> = {
  ok: { word: 'Working', tone: 'good' },
  warn: { word: 'Needs a look', tone: 'warn' },
  down: { word: 'Down', tone: 'bad' },
};

const PART_LABEL: Record<string, string> = {
  api: 'API',
  database: 'Database',
  redis: 'Redis',
  workers: 'Brain workers',
  queues: 'Message queues',
  dead_letters: 'Dead letters',
  agent: 'Voice agent',
  recordings: 'Recordings',
};

/** Platform home: one row per part of the system, then interviews running right now. */
export function HealthPage() {
  const health = usePlatformHealth();
  const sessions = useSessions('all');
  const live = (sessions.data ?? []).filter((s) => !s.interview_ended);
  const overall = health.data ? HEALTH_TONE[health.data.state] : null;

  const columns: Column<Part>[] = [
    { key: 'part', header: 'Part', render: (p) => <span className="font-medium">{PART_LABEL[p.part] ?? p.part}</span> },
    {
      key: 'state',
      header: 'State',
      width: 'w-40',
      render: (p) => <StatusLabel tone={HEALTH_TONE[p.state].tone}>{HEALTH_TONE[p.state].word}</StatusLabel>,
    },
    { key: 'detail', header: 'Detail', render: (p) => <span className="text-muted">{p.detail}</span> },
  ];

  return (
    <>
      <PageHeader
        title="Health"
        description="Each part of the system, checked every 10 seconds, and the interviews running right now."
        meta={
          overall && (
            <>
              <StatusLabel tone={overall.tone}>{overall.word}</StatusLabel>
              <span>Checked {formatRelative(health.data?.checked_at)}</span>
            </>
          )
        }
      />

      <Section title="System">
        {health.error ? (
          <ErrorState title="Health didn’t load" error={health.error} onRetry={() => health.refetch()} />
        ) : (
          <DataTable
            caption="System health"
            columns={columns}
            rows={health.data?.parts ?? []}
            rowKey={(p) => p.part}
            loading={health.isLoading}
          />
        )}
      </Section>

      <Section
        title="Live interviews"
        description="Not ended yet, across every organization. Rows with no activity for 15 minutes are probably abandoned."
      >
        {sessions.error ? (
          <ErrorState title="Sessions didn’t load" error={sessions.error} onRetry={() => sessions.refetch()} />
        ) : (
          <InterviewsTable
            rows={rowsFromSessions(live)}
            loading={sessions.isLoading}
            basePath="/platform/interviews"
            empty={<EmptyState title="Nothing running" body="No interview is in progress on any worker." />}
          />
        )}
      </Section>
    </>
  );
}

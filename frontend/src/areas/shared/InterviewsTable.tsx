import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { formatDateTime, minutesSince, percent, roundLabel } from '@/lib/format';
import type { CandidateInvite, OrgInterview, PlatformInterview } from '@/types';
import { DataTable, Input, StatusLabel, Tabs, type Column, type Tone } from '@/ui';
import type { SessionRow } from './data';
import { endReason } from './endReasons';

type Filter = 'all' | 'live' | 'completed' | 'invited';

export interface InterviewRow {
  key: string;
  sessionId: string | null;
  candidate: string;
  sub: string;
  role: string;
  /** Platform console only */
  org?: string;
  round: string;
  status: { word: string; tone: Tone; filter: Exclude<Filter, 'all'> };
  started: string | null;
  turns: string;
  integrity: number | null;
}

/** A running interview that hasn't changed for this long is probably abandoned */
const IDLE_MINUTES = 15;

function runningStatus(lastActivity: string | null | undefined): InterviewRow['status'] {
  const idle = minutesSince(lastActivity);
  if (idle != null && idle > IDLE_MINUTES) return { word: 'No activity', tone: 'warn', filter: 'live' };
  return { word: 'In progress', tone: 'live', filter: 'live' };
}

const COMPLETED: InterviewRow['status'] = { word: 'Completed', tone: 'good', filter: 'completed' };

/** Finished: "Completed", "Ended early" or "Incomplete", from how it ended. */
function finishedStatus(reason: string | null | undefined): InterviewRow['status'] {
  const r = endReason(reason);
  return r ? { word: r.status, tone: r.tone, filter: 'completed' } : COMPLETED;
}

/** Workspace: the organization's interviews (Postgres) plus invites nobody has used yet. */
export function rowsFromOrg(interviews: OrgInterview[], invites: CandidateInvite[]): InterviewRow[] {
  const rows: InterviewRow[] = interviews.map((i) => ({
    key: i.session_id,
    sessionId: i.session_id,
    candidate: i.candidate_name || 'Unnamed candidate',
    sub: i.candidate_email || i.session_id,
    role: i.role_title,
    round: roundLabel(i.interview_mode),
    status: i.status === 'completed' ? finishedStatus(i.end_reason) : runningStatus(i.last_activity),
    started: i.created_at,
    turns: String(i.turn_count),
    integrity: i.integrity_score,
  }));
  for (const inv of invites) {
    if (inv.status !== 'pending') continue;
    rows.push({
      key: inv.invite_id,
      sessionId: null,
      candidate: inv.candidate_name,
      sub: inv.candidate_email || 'Invite sent',
      role: inv.role_title,
      round: roundLabel(inv.interview_mode),
      status: { word: 'Invited', tone: 'neutral', filter: 'invited' },
      started: null,
      turns: '—',
      integrity: null,
    });
  }
  return rows;
}

/** Platform console: every organization's interviews (Postgres). */
export function rowsFromPlatform(interviews: PlatformInterview[]): InterviewRow[] {
  return interviews.map((i) => ({
    key: i.session_id,
    sessionId: i.session_id,
    candidate: i.candidate_name || 'Unnamed candidate',
    sub: i.candidate_email || i.session_id,
    role: i.role_title,
    org: i.org_name || (i.org_id ? i.org_id : 'No organization'),
    round: roundLabel(i.interview_mode),
    status: i.status === 'completed' ? finishedStatus(i.end_reason) : runningStatus(i.last_activity),
    started: i.created_at,
    turns: String(i.turn_count),
    integrity: i.integrity_score,
  }));
}

/** Platform health: live sessions in Redis across organizations. */
export function rowsFromSessions(sessions: SessionRow[]): InterviewRow[] {
  return sessions.map((s) => ({
    key: s.session_id,
    sessionId: s.session_id,
    candidate: s.candidate_id || 'Unnamed candidate',
    sub: s.session_id,
    role: '',
    round: '',
    status: s.interview_ended ? COMPLETED : runningStatus(s.last_updated ?? s.started_at),
    started: s.started_at ?? null,
    turns: String(s.turn_count),
    integrity: s.integrity_score ?? null,
  }));
}

const PAGE = 20;

interface InterviewsTableProps {
  rows: InterviewRow[];
  loading: boolean;
  /** "/app/interviews" or "/platform/interviews" */
  basePath: string;
  empty: React.ReactNode;
}

export function InterviewsTable({ rows, loading, basePath, empty }: InterviewsTableProps) {
  const [filter, setFilter] = useState<Filter>('all');
  const [query, setQuery] = useState('');

  const counts = useMemo(() => {
    const c = { all: rows.length, live: 0, completed: 0, invited: 0 };
    for (const r of rows) c[r.status.filter]++;
    return c;
  }, [rows]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter(
      (r) =>
        (filter === 'all' || r.status.filter === filter) &&
        (!q ||
          r.candidate.toLowerCase().includes(q) ||
          r.role.toLowerCase().includes(q) ||
          (r.org ?? '').toLowerCase().includes(q) ||
          r.sub.toLowerCase().includes(q)),
    );
  }, [rows, filter, query]);

  const columns: Column<InterviewRow>[] = [
    {
      key: 'candidate',
      header: 'Candidate',
      sortValue: (r) => r.candidate.toLowerCase(),
      render: (r) => (
        <div className="min-w-0">
          <div className="truncate font-medium text-ink">{r.candidate}</div>
          <div className="truncate font-mono text-[12px] text-muted">{r.sub}</div>
        </div>
      ),
    },
    {
      key: 'role',
      header: 'Role',
      sortValue: (r) => r.role || null,
      render: (r) => r.role || <span className="text-muted">—</span>,
      hideBelow: 'md',
    },
    // Only when the rows span more than one organization
    ...(new Set(rows.filter((r) => r.org !== undefined).map((r) => r.org)).size > 1
      ? [
          {
            key: 'org',
            header: 'Organization',
            sortValue: (r: InterviewRow) => r.org ?? null,
            render: (r: InterviewRow) => r.org || <span className="text-muted">—</span>,
            hideBelow: 'md' as const,
          },
        ]
      : []),
    { key: 'round', header: 'Round', render: (r) => r.round || <span className="text-muted">—</span>, hideBelow: 'lg' },
    {
      key: 'status',
      header: 'Status',
      sortValue: (r) => r.status.word,
      render: (r) => <StatusLabel tone={r.status.tone}>{r.status.word}</StatusLabel>,
    },
    {
      key: 'started',
      header: 'Started',
      numeric: true,
      sortValue: (r) => r.started,
      render: (r) => formatDateTime(r.started),
      hideBelow: 'sm',
    },
    { key: 'turns', header: 'Turns', numeric: true, align: 'right', render: (r) => r.turns, hideBelow: 'lg' },
    {
      key: 'integrity',
      header: 'Integrity',
      numeric: true,
      align: 'right',
      sortValue: (r) => r.integrity,
      render: (r) => (
        <span className={r.integrity != null && r.integrity < 0.7 ? 'text-bad' : undefined}>
          {percent(r.integrity)}
        </span>
      ),
      hideBelow: 'md',
    },
  ];

  const hasInvited = rows.some((r) => r.status.filter === 'invited');

  return (
    <div>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <Tabs
          label="Filter interviews"
          value={filter}
          onChange={setFilter}
          items={[
            { key: 'all', label: 'All', count: counts.all },
            { key: 'live', label: 'Not finished', count: counts.live },
            { key: 'completed', label: 'Completed', count: counts.completed },
            ...(hasInvited ? [{ key: 'invited' as const, label: 'Invited', count: counts.invited }] : []),
          ]}
        />
        <div className="relative sm:w-64">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
            aria-hidden
          />
          <Input
            type="search"
            aria-label="Search by candidate, role or session"
            placeholder="Search candidates"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>
      <DataTable
        caption="Interviews"
        columns={columns}
        rows={visible}
        pageSize={PAGE}
        pageResetKey={`${filter}|${query}`}
        rowKey={(r) => r.key}
        rowHref={(r) => (r.sessionId ? `${basePath}/${encodeURIComponent(r.sessionId)}` : undefined)}
        loading={loading}
        defaultSort={{ key: 'started', dir: 'desc' }}
        empty={rows.length === 0 ? empty : <p className="text-body text-muted">No interviews match.</p>}
      />
    </div>
  );
}

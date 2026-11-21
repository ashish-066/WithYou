import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type { RankingEntry } from '@/types';
import {
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  Section,
  Select,
  StatusLabel,
  type Column,
} from '@/ui';
import { useComparison, useOrgInterviews, useRankings, useRoles } from '../shared/data';

const humanize = (key: string) => {
  const s = key.replace(/[_-]+/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
};

/** Candidates ranked per job role; tick two to compare them skill by skill. */
export function RankingsPage() {
  const roles = useRoles();
  const interviews = useOrgInterviews();
  const [roleId, setRoleId] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [pair, setPair] = useState<[string, string] | null>(null);

  const roleList = roles.data ?? [];
  useEffect(() => {
    if (!roleId && roleList.length) setRoleId(roleList[0].role_id);
  }, [roleId, roleList]);

  const rankings = useRankings(roleId);
  const comparison = useComparison(roleId, pair);

  // Candidate names come from the organization's interviews (rankings carry session ids)
  const names = useMemo(() => {
    const m = new Map<string, { name: string; email: string }>();
    for (const i of interviews.data?.interviews ?? [])
      m.set(i.session_id, { name: i.candidate_name || 'Unnamed candidate', email: i.candidate_email });
    return m;
  }, [interviews.data]);
  const nameOf = (r: RankingEntry | undefined) =>
    (r?.session_id && names.get(r.session_id)?.name) || r?.candidate_id || 'Unknown';

  const rows = rankings.data?.rankings ?? [];
  const byId = new Map(rows.map((r) => [r.candidate_id, r]));

  const toggle = (id: string) => {
    setPair(null);
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length >= 2 ? [p[1], id] : [...p, id]));
  };

  const columns: Column<RankingEntry>[] = [
    {
      key: 'pick',
      header: <span className="sr-only">Compare</span>,
      width: 'w-10',
      render: (r) => (
        <input
          type="checkbox"
          aria-label={`Compare ${nameOf(r)}`}
          className="h-4 w-4 accent-[rgb(var(--c-accent))]"
          checked={picked.includes(r.candidate_id)}
          onChange={() => toggle(r.candidate_id)}
        />
      ),
    },
    { key: 'rank', header: 'Rank', numeric: true, width: 'w-16', sortValue: (r) => r.rank, render: (r) => r.rank ?? '—' },
    {
      key: 'candidate',
      header: 'Candidate',
      sortValue: (r) => nameOf(r).toLowerCase(),
      render: (r) =>
        r.session_id ? (
          <Link
            to={`/app/interviews/${encodeURIComponent(r.session_id)}`}
            className="font-medium text-ink underline-offset-2 hover:underline"
          >
            {nameOf(r)}
          </Link>
        ) : (
          <span className="font-medium text-ink">{nameOf(r)}</span>
        ),
    },
    { key: 'rating', header: 'Rating', numeric: true, align: 'right', sortValue: (r) => r.rating, render: (r) => Math.round(r.rating) },
    {
      key: 'record',
      header: 'Comparisons won',
      numeric: true,
      align: 'right',
      hideBelow: 'sm',
      render: (r) => `${r.wins} of ${r.matches_played}`,
    },
    {
      key: 'pct',
      header: 'Percentile',
      numeric: true,
      align: 'right',
      hideBelow: 'md',
      sortValue: (r) => r.percentile,
      render: (r) => (r.percentile == null ? '—' : `${Math.round(r.percentile)}`),
    },
  ];

  const c = comparison.data;
  const a = pair ? byId.get(pair[0]) : undefined;
  const b = pair ? byId.get(pair[1]) : undefined;

  return (
    <>
      <PageHeader
        title="Rankings"
        description="Candidates for one role, ranked by rating from their interviews. Tick two candidates to compare them."
      />

      {roles.error ? (
        <ErrorState title="Roles didn’t load" error={roles.error} onRetry={() => roles.refetch()} />
      ) : !roles.isLoading && roleList.length === 0 ? (
        <EmptyState title="No roles yet" body="Rankings are per job role. Add a role and invite candidates for it." />
      ) : (
        <>
          <div className="mb-6 flex flex-wrap items-end gap-3">
            <Field label="Role" className="w-full sm:w-72">
              {(f) => (
                <Select
                  id={f.id}
                  value={roleId ?? ''}
                  onChange={(e) => {
                    setRoleId(e.target.value);
                    setPicked([]);
                    setPair(null);
                  }}
                >
                  {roleList.map((r) => (
                    <option key={r.role_id} value={r.role_id}>
                      {r.role_title}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Button
              variant="primary"
              disabled={picked.length !== 2}
              onClick={() => setPair([picked[0], picked[1]])}
            >
              {picked.length === 2 ? 'Compare the two' : `Tick ${2 - picked.length} more to compare`}
            </Button>
          </div>

          {rankings.error ? (
            <ErrorState title="Rankings didn’t load" error={rankings.error} onRetry={() => rankings.refetch()} />
          ) : (
            <DataTable
              caption="Rankings"
              columns={columns}
              rows={rows}
              rowKey={(r) => r.candidate_id}
              loading={rankings.isLoading || roles.isLoading}
              defaultSort={{ key: 'rank', dir: 'asc' }}
              empty={
                <EmptyState
                  title="No ranked candidates yet"
                  body="Candidates appear here once their interview for this role is scored."
                />
              }
            />
          )}
          {rankings.data && !rankings.data.rankings_available && rows.length > 0 && (
            <p className="mt-3 text-meta text-muted">
              Ranks settle once at least {rankings.data.min_candidates_required} candidates have been scored.
            </p>
          )}

          {pair && (
            <Section title={`${nameOf(a)} and ${nameOf(b)}`} className="mt-10">
              {comparison.error ? (
                <ErrorState title="The comparison didn’t load" error={comparison.error} onRetry={() => comparison.refetch()} />
              ) : !c ? (
                <p className="text-meta text-muted">Comparing…</p>
              ) : (
                <>
                  <p className="mb-4 text-body text-ink">
                    {c.overall_winner === 'tie'
                      ? 'Overall, they are level.'
                      : `Overall, ${c.overall_winner === 'a' ? nameOf(a) : nameOf(b)} is ahead.`}
                  </p>
                  <DataTable
                    caption="Skill comparison"
                    rows={c.skill_comparisons}
                    rowKey={(s) => s.skill_name}
                    columns={[
                      { key: 'skill', header: 'Skill', render: (s) => humanize(s.skill_name) },
                      { key: 'a', header: nameOf(a), numeric: true, align: 'right', render: (s) => `${s.level_a} / 5` },
                      { key: 'b', header: nameOf(b), numeric: true, align: 'right', render: (s) => `${s.level_b} / 5` },
                      {
                        key: 'winner',
                        header: 'Stronger',
                        render: (s) =>
                          s.winner === 'tie' ? (
                            <span className="text-muted">Level</span>
                          ) : (
                            <StatusLabel tone="good">{s.winner === 'a' ? nameOf(a) : nameOf(b)}</StatusLabel>
                          ),
                      },
                    ]}
                  />
                </>
              )}
            </Section>
          )}
        </>
      )}
    </>
  );
}

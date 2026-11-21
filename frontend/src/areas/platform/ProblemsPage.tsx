import { useMemo, useState } from 'react';
import { Plus, Search } from 'lucide-react';
import { formatDate } from '@/lib/format';
import type { ProblemRow } from '@/types';
import { ButtonLink, DataTable, EmptyState, ErrorState, Input, PageHeader, StatusLabel, type Column, type Tone } from '@/ui';
import { usePlatformProblems } from '../shared/data';

export const DIFFICULTY: Record<string, { word: string; tone: Tone }> = {
  easy: { word: 'Easy', tone: 'good' },
  medium: { word: 'Medium', tone: 'warn' },
  hard: { word: 'Hard', tone: 'bad' },
};

/** The coding problems used in coding rounds, shared by every organization. */
export function ProblemsPage() {
  const problems = usePlatformProblems();
  const [query, setQuery] = useState('');
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (problems.data ?? []).filter(
      (p) =>
        !q ||
        p.title.toLowerCase().includes(q) ||
        p.problem_id.toLowerCase().includes(q) ||
        p.tags.some((t) => t.toLowerCase().includes(q)),
    );
  }, [problems.data, query]);

  const columns: Column<ProblemRow>[] = [
    {
      key: 'title',
      header: 'Problem',
      sortValue: (p) => p.title.toLowerCase(),
      render: (p) => (
        <div className="min-w-0">
          <div className="truncate font-medium text-ink">{p.title}</div>
          <div className="truncate font-mono text-[12px] text-muted">{p.problem_id}</div>
        </div>
      ),
    },
    {
      key: 'difficulty',
      header: 'Difficulty',
      sortValue: (p) => ['easy', 'medium', 'hard'].indexOf(p.difficulty),
      render: (p) => (
        <StatusLabel tone={DIFFICULTY[p.difficulty]?.tone}>{DIFFICULTY[p.difficulty]?.word ?? p.difficulty}</StatusLabel>
      ),
    },
    {
      key: 'tags',
      header: 'Topics',
      hideBelow: 'lg',
      render: (p) => (p.tags.length ? <span className="text-muted">{p.tags.join(', ')}</span> : null),
    },
    {
      key: 'tests',
      header: 'Tests',
      numeric: true,
      align: 'right',
      hideBelow: 'sm',
      render: (p) => (
        <span title={`${p.public_tests} visible, ${p.hidden_tests} hidden`}>
          {p.public_tests} + {p.hidden_tests}
        </span>
      ),
    },
    { key: 'used', header: 'Interviews', numeric: true, align: 'right', sortValue: (p) => p.interviews, render: (p) => p.interviews, hideBelow: 'md' },
    { key: 'created', header: 'Added', numeric: true, sortValue: (p) => p.created_at, render: (p) => formatDate(p.created_at), hideBelow: 'md' },
  ];

  return (
    <>
      <PageHeader
        title="Problem library"
        description="Coding problems for coding rounds, shared by every organization. Tests show as visible + hidden."
        actions={
          <ButtonLink to="/platform/problems/new" variant="primary" icon={<Plus className="h-4 w-4" aria-hidden />}>
            New problem
          </ButtonLink>
        }
      />
      <div className="mb-4 sm:w-64">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
          <Input
            type="search"
            aria-label="Search problems by title, id or topic"
            placeholder="Search problems"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>
      {problems.error ? (
        <ErrorState title="Problems didn’t load" error={problems.error} onRetry={() => problems.refetch()} />
      ) : (
        <DataTable
          caption="Coding problems"
          columns={columns}
          rows={visible}
          rowKey={(p) => p.problem_id}
          rowHref={(p) => `/platform/problems/${encodeURIComponent(p.problem_id)}`}
          loading={problems.isLoading}
          pageSize={25}
          pageResetKey={query}
          empty={
            <EmptyState
              title={query ? 'No match' : 'No problems yet'}
              body={query ? undefined : 'Coding rounds need at least one problem. Add one to get started.'}
              action={
                query ? undefined : (
                  <ButtonLink to="/platform/problems/new" variant="primary">
                    New problem
                  </ButtonLink>
                )
              }
            />
          }
        />
      )}
    </>
  );
}

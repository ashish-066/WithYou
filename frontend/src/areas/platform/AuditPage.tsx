import { useMemo, useState, type FormEvent } from 'react';
import { formatDateTime } from '@/lib/format';
import type { AuditEventRow, AuditFilters } from '@/types';
import {
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  Select,
  type Column,
} from '@/ui';
import { useAuditLog, usePlatformOrganizations } from '../shared/data';

const EMPTY: AuditFilters = {};

/** Who did what, newest first, with filters for organization, person, event and dates. */
export function AuditPage() {
  const [draft, setDraft] = useState<AuditFilters>(EMPTY);
  const [filters, setFilters] = useState<AuditFilters>(EMPTY);
  const log = useAuditLog(filters);
  const orgs = usePlatformOrganizations();

  const events = useMemo(() => log.data?.pages.flatMap((p) => p.events) ?? [], [log.data]);
  const actions = log.data?.pages[0]?.actions ?? [];
  const active = Object.values(filters).some(Boolean);

  const apply = (e: FormEvent) => {
    e.preventDefault();
    setFilters({ ...draft, actor: draft.actor?.trim() || undefined });
  };
  const set = (k: keyof AuditFilters) => (v: string) => setDraft((d) => ({ ...d, [k]: v || undefined }));

  const columns: Column<AuditEventRow>[] = [
    { key: 'at', header: 'When', numeric: true, render: (e) => <span className="whitespace-nowrap">{formatDateTime(e.at)}</span> },
    {
      key: 'who',
      header: 'Who',
      render: (e) =>
        e.actor_type === 'user' ? (
          <div className="min-w-0">
            <div className="truncate text-ink">{e.actor_name || e.actor_id || 'Unknown'}</div>
            {e.actor_email && <div className="truncate text-meta text-muted">{e.actor_email}</div>}
          </div>
        ) : (
          <span className="text-muted">{e.actor_type === 'candidate' ? 'Candidate' : 'System'}</span>
        ),
    },
    { key: 'action', header: 'Event', render: (e) => <span className="font-mono text-meta">{e.action}</span> },
    {
      key: 'target',
      header: 'On',
      hideBelow: 'md',
      render: (e) =>
        e.target_id ? (
          <span className="block max-w-[14rem] truncate font-mono text-meta text-muted" title={e.target_id}>
            {e.target_type ? `${e.target_type} ` : ''}
            {e.target_id}
          </span>
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    { key: 'org', header: 'Organization', hideBelow: 'lg', render: (e) => e.org_name || e.org_id || <span className="text-muted">—</span> },
    {
      key: 'details',
      header: 'Details',
      hideBelow: 'lg',
      render: (e) =>
        e.details ? (
          <span className="block max-w-[16rem] truncate font-mono text-[12px] text-muted" title={JSON.stringify(e.details)}>
            {JSON.stringify(e.details)}
          </span>
        ) : null,
    },
  ];

  return (
    <>
      <PageHeader title="Audit log" description="Sign-ins, invites, team changes, decisions and data access, newest first." />

      <form onSubmit={apply} className="mb-6 flex flex-wrap items-end gap-3">
        <Field label="Organization" className="w-full sm:w-48">
          {(p) => (
            <Select id={p.id} value={draft.org_id ?? ''} onChange={(e) => set('org_id')(e.target.value)}>
              <option value="">Any</option>
              {(orgs.data ?? []).map((o) => (
                <option key={o.org_id} value={o.org_id}>
                  {o.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Person" className="w-full sm:w-52">
          {(p) => (
            <Input
              id={p.id}
              placeholder="Email or user id"
              value={draft.actor ?? ''}
              onChange={(e) => set('actor')(e.target.value)}
            />
          )}
        </Field>
        <Field label="Event" className="w-full sm:w-48">
          {(p) => (
            <Select id={p.id} value={draft.action ?? ''} onChange={(e) => set('action')(e.target.value)}>
              <option value="">Any</option>
              {actions.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="From" className="w-[calc(50%-0.375rem)] sm:w-40">
          {(p) => <Input id={p.id} type="date" value={draft.since ?? ''} onChange={(e) => set('since')(e.target.value)} />}
        </Field>
        <Field label="To" className="w-[calc(50%-0.375rem)] sm:w-40">
          {(p) => <Input id={p.id} type="date" value={draft.until ?? ''} onChange={(e) => set('until')(e.target.value)} />}
        </Field>
        <div className="flex gap-2">
          <Button type="submit" variant="primary">
            Filter
          </Button>
          {active && (
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setDraft(EMPTY);
                setFilters(EMPTY);
              }}
            >
              Clear
            </Button>
          )}
        </div>
      </form>

      {log.error ? (
        <ErrorState title="The audit log didn’t load" error={log.error} onRetry={() => log.refetch()} />
      ) : (
        <>
          <DataTable
            caption="Audit events"
            columns={columns}
            rows={events}
            rowKey={(e) => String(e.id)}
            loading={log.isLoading}
            empty={<EmptyState title={active ? 'Nothing matches these filters' : 'No events yet'} />}
          />
          {log.hasNextPage && (
            <div className="mt-4 flex justify-center">
              <Button loading={log.isFetchingNextPage} onClick={() => log.fetchNextPage()}>
                Load older events
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}

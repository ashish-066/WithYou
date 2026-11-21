import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { formatDate, formatRelative } from '@/lib/format';
import type { PlatformOrganization } from '@/types';
import { DataTable, EmptyState, ErrorState, Input, PageHeader, type Column } from '@/ui';
import { usePlatformOrganizations } from '../shared/data';

export function OrganizationsPage() {
  const orgs = usePlatformOrganizations();
  const [query, setQuery] = useState('');
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (orgs.data ?? []).filter((o) => !q || o.name.toLowerCase().includes(q) || o.org_id.includes(q));
  }, [orgs.data, query]);

  const columns: Column<PlatformOrganization>[] = [
    {
      key: 'name',
      header: 'Organization',
      sortValue: (o) => o.name.toLowerCase(),
      render: (o) => (
        <div className="min-w-0">
          <div className="truncate font-medium text-ink">{o.name}</div>
          <div className="truncate font-mono text-[12px] text-muted">{o.org_id}</div>
        </div>
      ),
    },
    { key: 'members', header: 'Members', numeric: true, align: 'right', sortValue: (o) => o.members, render: (o) => o.members },
    { key: 'interviews', header: 'Interviews', numeric: true, align: 'right', sortValue: (o) => o.interviews, render: (o) => o.interviews },
    {
      key: 'active',
      header: 'Last active',
      sortValue: (o) => o.last_active,
      render: (o) => (o.last_active ? formatRelative(o.last_active) : <span className="text-muted">Never</span>),
      hideBelow: 'sm',
    },
    { key: 'created', header: 'Created', numeric: true, sortValue: (o) => o.created_at, render: (o) => formatDate(o.created_at), hideBelow: 'md' },
  ];

  return (
    <>
      <PageHeader title="Organizations" description="Every organization using Presence View." />
      <div className="mb-4 sm:w-64">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
          <Input
            type="search"
            aria-label="Search organizations"
            placeholder="Search organizations"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>
      {orgs.error ? (
        <ErrorState title="Organizations didn’t load" error={orgs.error} onRetry={() => orgs.refetch()} />
      ) : (
        <DataTable
          caption="Organizations"
          columns={columns}
          rows={visible}
          rowKey={(o) => o.org_id}
          rowHref={(o) => `/platform/organizations/${encodeURIComponent(o.org_id)}`}
          loading={orgs.isLoading}
          pageSize={25}
          pageResetKey={query}
          defaultSort={{ key: 'created', dir: 'desc' }}
          empty={<EmptyState title={query ? 'No match' : 'No organizations yet'} />}
        />
      )}
    </>
  );
}

import { useParams } from 'react-router-dom';
import { formatDate, formatRelative } from '@/lib/format';
import { ApiError } from '@/lib/api';
import type { PlatformOrganizationDetail } from '@/types';
import {
  ButtonLink,
  DataTable,
  DefinitionList,
  EmptyState,
  ErrorState,
  PageHeader,
  Section,
  Spinner,
  type Column,
} from '@/ui';
import { usePlatformOrganization } from '../shared/data';
import { InterviewsTable, rowsFromPlatform } from '../shared/InterviewsTable';

type Member = PlatformOrganizationDetail['members'][number];

export function OrganizationPage() {
  const { orgId = '' } = useParams();
  const org = usePlatformOrganization(orgId);
  const back = { to: '/platform/organizations', label: 'Organizations' };

  if (org.isLoading) {
    return (
      <div className="py-16">
        <Spinner label="Loading the organization" />
      </div>
    );
  }
  if (org.error || !org.data) {
    const notFound = org.error instanceof ApiError && org.error.status === 404;
    return (
      <>
        <PageHeader title="Organization" back={back} />
        {notFound ? (
          <EmptyState title="Organization not found" action={<ButtonLink to={back.to}>Back to organizations</ButtonLink>} />
        ) : (
          <ErrorState title="The organization didn’t load" error={org.error} onRetry={() => org.refetch()} />
        )}
      </>
    );
  }

  const d = org.data;
  const memberColumns: Column<Member>[] = [
    {
      key: 'name',
      header: 'Name',
      sortValue: (m) => m.name.toLowerCase(),
      render: (m) => (
        <div className="min-w-0">
          <div className="truncate font-medium text-ink">{m.name}</div>
          <div className="truncate text-meta text-muted">{m.email}</div>
        </div>
      ),
    },
    {
      key: 'role',
      header: 'Access',
      render: (m) => (m.role === 'admin' ? 'Admin' : 'Recruiter') + (m.is_platform_admin ? ', platform admin' : ''),
    },
    { key: 'added', header: 'Added', numeric: true, sortValue: (m) => m.created_at, render: (m) => formatDate(m.created_at), hideBelow: 'sm' },
  ];

  return (
    <>
      <PageHeader back={back} title={d.name} meta={<span className="font-mono">{d.org_id}</span>} />
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0">
          <Section title="Members" description={`${d.members_count} ${d.members_count === 1 ? 'person' : 'people'}`}>
            <DataTable caption="Members" columns={memberColumns} rows={d.members} rowKey={(m) => m.user_id} />
          </Section>
          <Section title="Recent interviews" description="The newest 50.">
            <InterviewsTable
              rows={rowsFromPlatform(d.recent_interviews)}
              loading={false}
              basePath="/platform/interviews"
              empty={<EmptyState title="No interviews yet" />}
            />
          </Section>
        </div>
        <aside>
          <DefinitionList
            items={[
              { term: 'Created', value: formatDate(d.created_at) },
              { term: 'Members', value: <span className="tabular">{d.members_count}</span> },
              { term: 'Interviews', value: <span className="tabular">{d.interviews_count}</span> },
              { term: 'Last active', value: d.last_active ? formatRelative(d.last_active) : 'Never' },
            ]}
          />
        </aside>
      </div>
    </>
  );
}

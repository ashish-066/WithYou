import { useMemo } from 'react';
import { Plus } from 'lucide-react';
import { ButtonLink, EmptyState, ErrorState, PageHeader } from '@/ui';
import { useInvites, useOrgInterviews } from '../shared/data';
import { InterviewsTable, rowsFromOrg } from '../shared/InterviewsTable';

/** Home of the workspace: every interview in the organization, and who is still invited. */
export function InterviewsPage() {
  const interviews = useOrgInterviews();
  const invites = useInvites();
  const error = interviews.error ?? invites.error;
  const rows = useMemo(
    () => rowsFromOrg(interviews.data?.interviews ?? [], invites.data ?? []),
    [interviews.data, invites.data],
  );

  return (
    <>
      <PageHeader
        title="Interviews"
        description="Everyone you’ve invited, interviews in progress and finished ones. In-progress rows update every few seconds."
        actions={
          <ButtonLink to="/app/invites?new=1" variant="primary" icon={<Plus className="h-4 w-4" aria-hidden />}>
            New invite
          </ButtonLink>
        }
      />
      {error ? (
        <ErrorState
          title="Interviews didn’t load"
          error={error}
          onRetry={() => {
            interviews.refetch();
            invites.refetch();
          }}
        />
      ) : (
        <InterviewsTable
          rows={rows}
          loading={interviews.isLoading || invites.isLoading}
          basePath="/app/interviews"
          empty={
            <EmptyState
              title="No interviews yet"
              body="Create an invite link and send it to a candidate. Their interview appears here as soon as they start."
              action={
                <ButtonLink to="/app/invites?new=1" variant="primary">
                  New invite
                </ButtonLink>
              }
            />
          }
        />
      )}
    </>
  );
}

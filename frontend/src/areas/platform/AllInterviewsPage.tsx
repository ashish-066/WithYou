import { useState } from 'react';
import { Checkbox, EmptyState, ErrorState, PageHeader } from '@/ui';
import { usePlatformInterviews } from '../shared/data';
import { InterviewsTable, rowsFromPlatform } from '../shared/InterviewsTable';

/** Every organization's interviews, with an Organization column. */
export function AllInterviewsPage() {
  const [unowned, setUnowned] = useState(false);
  const interviews = usePlatformInterviews(unowned);

  return (
    <>
      <PageHeader
        title="All interviews"
        description="Every organization’s interviews, newest first. Open one to see its report and internals."
        actions={
          <Checkbox
            label="Show sessions without an organization"
            checked={unowned}
            onChange={(e) => setUnowned(e.target.checked)}
          />
        }
      />
      {interviews.error ? (
        <ErrorState title="Interviews didn’t load" error={interviews.error} onRetry={() => interviews.refetch()} />
      ) : (
        <InterviewsTable
          rows={rowsFromPlatform(interviews.data?.interviews ?? [])}
          loading={interviews.isLoading}
          basePath="/platform/interviews"
          empty={
            <EmptyState title="No interviews yet" body="Interviews appear here as soon as any organization’s candidate starts." />
          }
        />
      )}
      {interviews.data?.truncated && (
        <p className="mt-3 text-meta text-muted">Showing the newest {interviews.data.total}. Older interviews aren’t listed yet.</p>
      )}
    </>
  );
}

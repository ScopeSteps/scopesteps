import { useParams } from 'react-router';

import { PageBody } from '@/app/shell/PageBody';
import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { EmptyState } from '@/components/EmptyState';
import { VersionCompare, versionName } from '@/features/backlog';
import { useProject } from '@/features/projects';
import { describeError } from '@/lib/apiError';

/**
 * Change requests and the comparison of approved versions. Requests themselves have no API yet,
 * so the list is an honest empty state; the comparison is live.
 */
export function ChangeRequestsPage() {
  const { projectId = '' } = useParams();
  const { data: project, error, isPending, refetch } = useProject(projectId);

  if (!projectId) {
    return null;
  }
  const baseline = project?.status.baseline_version ?? null;
  return (
    <PageBody>
      <p className="text-muted">
        Every request to change the approved scope, what it would change, and how it was decided.
      </p>
      {isPending ? (
        <p role="status" className="text-subtle">
          Loading the project…
        </p>
      ) : error ? (
        <Banner
          tone="bad"
          role="alert"
          action={
            <Button size="sm" onClick={() => void refetch()}>
              Try again
            </Button>
          }
        >
          Could not load the project. {describeError(error)}
        </Banner>
      ) : baseline === null ? (
        <EmptyState title="No baseline to change yet">
          <p>
            Change requests start after the first baseline is approved, so there’s something to
            compare against.
          </p>
        </EmptyState>
      ) : (
        <>
          <EmptyState title="No change requests yet">
            <p>
              Requests to change the scope will be listed here, each compared with{' '}
              {versionName(baseline)}, the current baseline.
            </p>
          </EmptyState>
          <VersionCompare projectId={projectId} />
        </>
      )}
    </PageBody>
  );
}

import { useParams } from 'react-router';

import { backlogPath, chatPath } from '@/app/paths';
import { PageBody } from '@/app/shell/PageBody';
import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { EmptyState } from '@/components/EmptyState';
import { ScopeConflictBanner, VersionCompare, versionName } from '@/features/backlog';
import { ChangeRequestList } from '@/features/change-control';
import { useProject } from '@/features/projects';
import { describeError } from '@/lib/apiError';

/**
 * Every change request with its status, summary and outcome, linking to its candidate and the
 * chat, and the comparison of approved versions.
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
          <ChangeRequestList
            projectId={projectId}
            empty={
              <EmptyState title="No change requests yet">
                <p>
                  Requests to change the scope will be listed here, each compared with{' '}
                  {versionName(baseline)}, the current baseline. Send one from the chat with the
                  Change request toggle.
                </p>
              </EmptyState>
            }
            versionHref={(versionId) => `${backlogPath(projectId)}?version=${versionId}`}
            chatHref={(runId) => `${chatPath(projectId)}?run=${runId}`}
            renderConflict={(request) =>
              request.candidate_version_id ? (
                <ScopeConflictBanner
                  projectId={projectId}
                  versionId={request.candidate_version_id}
                  evidenceHref={(decisionId) =>
                    `${backlogPath(projectId)}?version=${request.candidate_version_id ?? ''}&evidence=decision:${decisionId}`
                  }
                />
              ) : null
            }
          />
          <VersionCompare projectId={projectId} />
        </>
      )}
    </PageBody>
  );
}

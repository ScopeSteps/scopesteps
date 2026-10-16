import { Navigate, useLocation, useParams, useSearchParams } from 'react-router';

import { backlogPath, changesPath, chatPath } from '@/app/paths';
import { PageBody } from '@/app/shell/PageBody';
import { Banner } from '@/components/Banner';
import { ButtonLink } from '@/components/ButtonLink';
import { EmptyState } from '@/components/EmptyState';
import { isActive, lastRunId, openQuestions, useRun } from '@/features/agent-runs';
import { BacklogView, useBacklogVersion } from '@/features/backlog';
import { useProject } from '@/features/projects';
import { ApiError } from '@/lib/apiError';

/** Router state left when an unknown version in the URL was replaced by the project's own. */
interface MissingVersionState {
  missingVersion: string;
}

function isMissingVersionState(state: unknown): state is MissingVersionState {
  return (
    typeof state === 'object' &&
    state !== null &&
    'missingVersion' in state &&
    typeof state.missingVersion === 'string'
  );
}

/** The API's answer that a version id names nothing in this project, or is not an id at all. */
function isUnknownVersion(error: Error | null): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 422);
}

/**
 * The version in view comes from the URL: a version id, or a run id whose saved candidate is
 * shown. Without either, the last run started in this browser stands in, and without that, the
 * project's draft in progress or its current baseline.
 */
export function BacklogPage() {
  const { projectId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const urlVersionId = searchParams.get('version');
  const runId = urlVersionId ? null : (searchParams.get('run') ?? lastRunId(projectId));
  const { data: run, isPending } = useRun(runId);
  const project = useProject(projectId);
  const scope = project.data?.status;
  const projectVersionId = scope ? (scope.open_version_id ?? scope.baseline_version_id) : null;
  const requested = useBacklogVersion(projectId, urlVersionId);
  const versionId = urlVersionId ?? run?.candidate_version_id ?? (runId ? null : projectVersionId);
  const missing = isMissingVersionState(location.state) ? location.state.missingVersion : null;

  if (!projectId) {
    return null;
  }
  if (
    urlVersionId &&
    isUnknownVersion(requested.error) &&
    projectVersionId &&
    projectVersionId !== urlVersionId
  ) {
    return (
      <Navigate
        replace
        to={`${backlogPath(projectId)}?version=${projectVersionId}`}
        state={{ missingVersion: urlVersionId } satisfies MissingVersionState}
      />
    );
  }
  if (urlVersionId && isUnknownVersion(requested.error) && project.isPending) {
    return (
      <PageBody>
        <p role="status" className="text-subtle">
          Loading the backlog…
        </p>
      </PageBody>
    );
  }
  if (versionId) {
    return (
      <PageBody>
        {missing && (
          <Banner tone="warn" role="status">
            The link named a version that isn’t part of this project, so its latest version is shown
            instead.
          </Banner>
        )}
        <BacklogView
          projectId={projectId}
          versionId={versionId}
          changesHref={changesPath(projectId)}
        />
      </PageBody>
    );
  }
  if ((runId && isPending) || (!runId && project.isPending)) {
    return (
      <PageBody>
        <p role="status" className="text-subtle">
          Loading the backlog…
        </p>
      </PageBody>
    );
  }
  if (run && isActive(run)) {
    const waiting = openQuestions(run).length > 0;
    return (
      <EmptyState
        title="Your backlog appears here"
        action={
          <ButtonLink variant="primary" to={`${chatPath(projectId)}?run=${run.id}`}>
            {waiting ? 'Go to the questions' : 'Back to chat'}
          </ButtonLink>
        }
      >
        <p>
          The agent drafts epics and stories after its questions are answered or skipped. Every
          detail links back to a source.
        </p>
      </EmptyState>
    );
  }
  return (
    <EmptyState
      title="No backlog yet"
      action={<ButtonLink to={chatPath(projectId)}>Back to chat</ButtonLink>}
    >
      <p>
        After the agent’s first run, it drafts epics and stories here. Every detail will link back
        to a source.
      </p>
    </EmptyState>
  );
}

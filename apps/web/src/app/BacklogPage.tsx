import { useState } from 'react';

import { Navigate, useLocation, useParams, useSearchParams } from 'react-router';

import {
  backlogPath,
  changeRequestPath,
  changesPath,
  chatPath,
  requestChangePath,
} from '@/app/paths';
import { PageBody } from '@/app/shell/PageBody';
import { Banner } from '@/components/Banner';
import { ButtonLink } from '@/components/ButtonLink';
import { EmptyState } from '@/components/EmptyState';
import {
  CoveragePanel,
  draftingText,
  isActive,
  lastRunId,
  openQuestions,
  useRun,
  useTaskSuggestions,
} from '@/features/agent-runs';
import { BacklogView, useBacklogVersion } from '@/features/backlog';
import type { ItemDiscussions } from '@/features/backlog';
import { DiscussionSheet, useThreadCounts } from '@/features/discussions';
import { useCan } from '@/features/identity';
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

/** What the run that wrote a version's draft covers; nothing for a version no initial run wrote. */
function RunCoverage({ projectId, runId }: { projectId: string; runId: string | null }) {
  const { data: run } = useRun(runId);
  if (run?.mode !== 'initial' || !run.coverage) {
    return null;
  }
  return <CoveragePanel projectId={projectId} run={run} coverage={run.coverage} />;
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
  // The run that drafts the backlog is advanced from the chat, so this page only watches it.
  const { data: run, isPending } = useRun(runId, { watch: true });
  const project = useProject(projectId);
  const scope = project.data?.status;
  const projectVersionId = scope ? (scope.open_version_id ?? scope.baseline_version_id) : null;
  const requested = useBacklogVersion(projectId, urlVersionId);
  const versionId = urlVersionId ?? run?.candidate_version_id ?? (runId ? null : projectVersionId);
  const missing = isMissingVersionState(location.state) ? location.state.missingVersion : null;
  const canEdit = useCan(projectId, 'edit_backlog');
  const taskSuggestions = useTaskSuggestions(projectId, versionId, canEdit);
  const threadCounts = useThreadCounts(projectId);
  const [discussing, setDiscussing] = useState<{ id: string; title: string } | null>(null);
  const discussions: ItemDiscussions = {
    counts: Object.fromEntries(
      (threadCounts.data?.items ?? []).map((count) => [count.item_id, count.open_threads]),
    ),
    onOpen: setDiscussing,
  };

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
          discussions={discussions}
          renderSummary={(version) => <RunCoverage projectId={projectId} runId={version.run_id} />}
          taskSuggestions={taskSuggestions}
        />
        {discussing && (
          <DiscussionSheet
            projectId={projectId}
            item={discussing}
            links={{
              requestChangeHref: (threadId) => requestChangePath(projectId, threadId),
              changeRequestHref: (id) => changeRequestPath(projectId, id),
            }}
            onClose={() => {
              setDiscussing(null);
            }}
          />
        )}
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
    const progress = draftingText(run);
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
        <p role="status" className="font-medium text-fg">
          {progress && `${progress} The work moves on while the chat is open.`}
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

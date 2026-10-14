import { useParams, useSearchParams } from 'react-router';

import { chatPath } from '@/app/paths';
import { PageBody } from '@/app/shell/PageBody';
import { ButtonLink } from '@/components/ButtonLink';
import { EmptyState } from '@/components/EmptyState';
import { isActive, lastRunId, openQuestions, useRun } from '@/features/agent-runs';
import { BacklogView } from '@/features/backlog';

/**
 * The draft in view comes from the URL: a version id, or a run id whose saved candidate is
 * shown. Without either, the last run started in this browser stands in, because the API
 * cannot yet list a project's runs or versions.
 */
export function BacklogPage() {
  const { projectId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const urlVersionId = searchParams.get('version');
  const runId = urlVersionId ? null : (searchParams.get('run') ?? lastRunId(projectId));
  const { data: run, isPending } = useRun(runId);
  const versionId = urlVersionId ?? run?.candidate_version_id ?? null;

  if (!projectId) {
    return null;
  }
  if (versionId) {
    return (
      <PageBody>
        <BacklogView projectId={projectId} versionId={versionId} />
      </PageBody>
    );
  }
  if (runId && isPending) {
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

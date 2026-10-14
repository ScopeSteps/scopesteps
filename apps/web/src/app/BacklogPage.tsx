import { useParams, useSearchParams } from 'react-router';

import { PageBody } from '@/app/shell/PageBody';
import { AgentRunView, useRun } from '@/features/agent-runs';
import { BacklogView } from '@/features/backlog';

export function BacklogPage() {
  const { projectId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  // The run and version ids live in the URL, so a refresh or a shared link restores the view.
  const runId = searchParams.get('run');
  const { data: run } = useRun(runId);
  if (!projectId) {
    return null;
  }
  const versionId = run?.candidate_version_id ?? (runId ? null : searchParams.get('version'));

  return (
    <PageBody>
      {(runId !== null || versionId === null) && (
        <AgentRunView
          projectId={projectId}
          runId={runId}
          onRunSelected={(selected) => {
            setSearchParams(selected ? { run: selected } : {});
          }}
        />
      )}
      {versionId && <BacklogView projectId={projectId} versionId={versionId} />}
    </PageBody>
  );
}

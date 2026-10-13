import { Link, useParams, useSearchParams } from 'react-router';

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
    <main className="mx-auto max-w-4xl space-y-8 p-8">
      <div>
        <nav aria-label="Project" className="flex gap-4 text-sm">
          <Link to="/" className="text-blue-800 underline">
            ← Home
          </Link>
          <Link to={`/projects/${projectId}/sources`} className="text-blue-800 underline">
            Sources
          </Link>
        </nav>
        <h1 className="mt-2 text-2xl font-semibold">Backlog</h1>
      </div>
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
    </main>
  );
}

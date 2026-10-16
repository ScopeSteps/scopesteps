import { useParams, useSearchParams } from 'react-router';

import { backlogPath, changesPath } from '@/app/paths';
import { ChatView } from '@/features/agent-runs';

/**
 * The chat fills the page itself, so its composer stays at the bottom; it is the one page
 * that does not lay out in `PageBody`.
 */
export function ChatPage() {
  const { projectId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  if (!projectId) {
    return null;
  }

  return (
    <ChatView
      projectId={projectId}
      // The run started here stays in the URL for the run details in the top bar.
      runId={searchParams.get('run')}
      onRunSelected={(runId) => {
        setSearchParams(runId ? { run: runId } : {});
      }}
      backlogHref={(versionId) => `${backlogPath(projectId)}?version=${versionId}`}
      changesHref={changesPath(projectId)}
    />
  );
}

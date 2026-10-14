import { useParams, useSearchParams } from 'react-router';

import { backlogPath } from '@/app/paths';
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
      // The run id lives in the URL, so a refresh or a shared link restores the thread.
      runId={searchParams.get('run')}
      onRunSelected={(runId) => {
        setSearchParams(runId ? { run: runId } : {});
      }}
      backlogHref={(versionId) => `${backlogPath(projectId)}?version=${versionId}`}
    />
  );
}

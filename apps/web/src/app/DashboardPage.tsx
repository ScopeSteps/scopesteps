import { useParams } from 'react-router';

import { backlogPath, changesPath, chatPath, sourcesPath, teamPath } from '@/app/paths';
import { PageBody } from '@/app/shell/PageBody';
import { DashboardView } from '@/features/projects';

/** Where the project's scope stands, for every member; each figure opens its details. */
export function DashboardPage() {
  const { projectId } = useParams();
  if (!projectId) {
    return null;
  }
  return (
    <PageBody>
      <DashboardView
        projectId={projectId}
        links={{
          backlog: (versionId) =>
            versionId ? `${backlogPath(projectId)}?version=${versionId}` : backlogPath(projectId),
          chat: chatPath(projectId),
          changes: changesPath(projectId),
          team: teamPath(projectId),
          sources: sourcesPath(projectId),
        }}
      />
    </PageBody>
  );
}

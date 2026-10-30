import { useParams } from 'react-router';

import { PageBody } from '@/app/shell/PageBody';
import { DiscussionPanel } from '@/features/discussions';

/** General discussion and every thread in the project, for talk outside meetings. */
export function DiscussionPage() {
  const { projectId } = useParams();
  if (!projectId) {
    return null;
  }

  return (
    <PageBody>
      <p className="text-muted">
        Ideas and questions about scope, written down where the whole team can see them. A
        discussion never changes the backlog.
      </p>
      <DiscussionPanel projectId={projectId} scope={{ kind: 'project' }} />
    </PageBody>
  );
}

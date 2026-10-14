import { useParams } from 'react-router';

import { PageBody } from '@/app/shell/PageBody';
import { ActivityView } from '@/features/activity';

export function ActivityPage() {
  const { projectId } = useParams();
  if (!projectId) {
    return null;
  }

  return (
    <PageBody>
      <ActivityView projectId={projectId} />
    </PageBody>
  );
}

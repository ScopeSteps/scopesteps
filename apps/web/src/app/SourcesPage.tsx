import { useParams } from 'react-router';

import { PageBody } from '@/app/shell/PageBody';
import { SourcesView } from '@/features/sources';

export function SourcesPage() {
  const { projectId } = useParams();
  if (!projectId) {
    return null;
  }

  return (
    <PageBody>
      <SourcesView projectId={projectId} />
    </PageBody>
  );
}

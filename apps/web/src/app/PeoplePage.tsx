import { useParams } from 'react-router';

import { PageBody } from '@/app/shell/PageBody';
import { PeopleView } from '@/features/projects';

export function PeoplePage() {
  const { projectId } = useParams();
  if (!projectId) {
    return null;
  }

  return (
    <PageBody>
      <PeopleView projectId={projectId} />
    </PageBody>
  );
}

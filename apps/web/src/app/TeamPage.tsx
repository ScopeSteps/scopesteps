import { useNavigate, useParams } from 'react-router';

import { PageBody } from '@/app/shell/PageBody';
import { ProjectMembers } from '@/features/projects';

/** Everyone on the project with their role; an Approver invites people and changes roles here. */
export function TeamPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  if (!projectId) {
    return null;
  }

  return (
    <PageBody>
      <ProjectMembers
        projectId={projectId}
        layout="page"
        onLeft={() => {
          void navigate('/', { replace: true });
        }}
      />
    </PageBody>
  );
}

import { useParams } from 'react-router';

import { ProjectShell } from './ProjectShell';
import { ShellFrame } from './ShellFrame';

/** The layout every route renders in: sidebar, top bar and the page. */
export function AppShell() {
  const { projectId } = useParams();
  return projectId ? <ProjectShell projectId={projectId} /> : <ShellFrame project={null} />;
}

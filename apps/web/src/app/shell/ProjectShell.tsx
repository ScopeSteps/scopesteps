import { ShellFrame } from './ShellFrame';
import { useProjectStatus } from './useProjectStatus';

interface ProjectShellProps {
  projectId: string;
}

/** The shell for a page inside a project, with that project's status in the frame. */
export function ProjectShell({ projectId }: ProjectShellProps) {
  return <ShellFrame project={useProjectStatus(projectId)} />;
}

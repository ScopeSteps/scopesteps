import type { ProjectStatus } from './projectStatus';

interface ProjectCardProps {
  project: ProjectStatus;
}

/**
 * The project in view. The API names a project only by its id until projects have their own
 * endpoints, so the id is shown as it is returned.
 */
export function ProjectCard({ project }: ProjectCardProps) {
  return (
    <div className="mb-3.5 flex flex-col gap-0.5 rounded-[10px] border border-line bg-surface p-2.5">
      <span className="text-[11px] font-semibold tracking-[0.07em] text-subtle uppercase">
        Project
      </span>
      <span className="font-mono text-xs font-medium break-all tabular-nums">
        {project.projectId}
      </span>
      {project.chip && <span className="text-xs text-subtle">{project.chip.text}</span>}
    </div>
  );
}

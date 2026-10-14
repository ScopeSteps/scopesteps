import { useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';

import { switchProjectPath } from '@/app/paths';
import { Icon } from '@/components/Icon';
import { ProjectMenu, projectStatusText, useProject } from '@/features/projects';

interface ProjectCardProps {
  projectId: string;
  onNavigate: () => void;
  onNewProject: () => void;
  onOpenSettings: () => void;
}

/** The project in view, by its name and scope status, and the menu to switch projects. */
export function ProjectCard({
  projectId,
  onNavigate,
  onNewProject,
  onOpenSettings,
}: ProjectCardProps) {
  const { data: project, isPending } = useProject(projectId);
  const [menuOpen, setMenuOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();
  const { pathname } = useLocation();

  let name: string;
  let status: string;
  if (project) {
    name = project.name;
    status = projectStatusText(project.status);
  } else if (isPending) {
    name = 'Loading project…';
    status = '';
  } else {
    name = 'Project unavailable';
    status = 'It may have been removed, or you are not a member.';
  }

  return (
    <div className="relative mb-3.5">
      <button
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        // The menu closes itself when focus leaves it; without this the same click reopens it.
        onMouseDown={(event) => {
          if (menuOpen) {
            event.preventDefault();
          }
        }}
        onClick={() => {
          setMenuOpen((open) => !open);
        }}
        className="flex w-full cursor-pointer flex-col gap-0.5 rounded-[10px] border border-line bg-surface p-2.5 text-left hover:border-line-strong"
      >
        <span className="text-[11px] font-semibold tracking-[0.07em] text-subtle uppercase">
          Project
        </span>
        {/* The spaces keep the parts apart in the button's accessible name. */}{' '}
        <span className="flex items-center justify-between gap-2">
          <strong className="min-w-0 truncate font-semibold">{name}</strong>
          <Icon name="more" size={16} />
        </span>{' '}
        {status && <span className="text-xs text-subtle">{status}</span>}
      </button>
      {menuOpen && (
        <ProjectMenu
          currentProjectId={projectId}
          trigger={trigger}
          onClose={() => {
            setMenuOpen(false);
          }}
          onSwitch={(nextProjectId) => {
            setMenuOpen(false);
            onNavigate();
            if (nextProjectId !== projectId) {
              void navigate(switchProjectPath(pathname, nextProjectId));
            }
          }}
          onNewProject={() => {
            setMenuOpen(false);
            onNewProject();
          }}
          onOpenSettings={() => {
            setMenuOpen(false);
            onOpenSettings();
          }}
        />
      )}
    </div>
  );
}

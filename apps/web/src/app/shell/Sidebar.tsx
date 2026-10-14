import type { Ref } from 'react';
import { Link } from 'react-router';

import { BrandMark } from '@/components/BrandMark';
import { IconButton } from '@/components/IconButton';

import { AccountMenu } from './AccountMenu';
import { ProjectCard } from './ProjectCard';
import { ProjectNav } from './ProjectNav';
import type { ProjectStatus } from './projectStatus';

interface SidebarProps {
  id: string;
  project: ProjectStatus | null;
  isDrawer: boolean;
  onHide: () => void;
  onNavigate: () => void;
  onOpenSettings: () => void;
  hideRef: Ref<HTMLButtonElement>;
}

export function Sidebar({
  id,
  project,
  isDrawer,
  onHide,
  onNavigate,
  onOpenSettings,
  hideRef,
}: SidebarProps) {
  return (
    <aside
      id={id}
      aria-label="Main navigation"
      className="flex h-full min-h-0 flex-col border-r border-line bg-surface-2 px-2.5 py-3"
    >
      <div className="flex items-center justify-between px-1.5 pt-1 pb-3">
        <Link
          to="/"
          onClick={onNavigate}
          className="flex items-center gap-2 text-base font-bold tracking-[-0.01em]"
        >
          <BrandMark />
          ScopeSteps
        </Link>
        <IconButton
          ref={hideRef}
          icon={isDrawer ? 'close' : 'panel'}
          label={isDrawer ? 'Close menu' : 'Hide sidebar'}
          aria-expanded={true}
          aria-controls={id}
          onClick={onHide}
        />
      </div>
      {project && (
        <>
          <ProjectCard project={project} />
          <ProjectNav project={project} onNavigate={onNavigate} />
        </>
      )}
      <div className="mt-auto pt-2">
        <AccountMenu roleLabel={project?.roleLabel ?? null} onOpenSettings={onOpenSettings} />
      </div>
    </aside>
  );
}

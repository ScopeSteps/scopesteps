import type { Ref } from 'react';

import { IconButton } from '@/components/IconButton';
import { Tag } from '@/components/Tag';
import { RunDetailsButton } from '@/features/agent-runs';

import { NextStepPill } from './NextStepPill';
import type { ProjectStatus } from './projectStatus';

interface TopBarProps {
  title: string;
  project: ProjectStatus | null;
  sidebarVisible: boolean;
  isDrawer: boolean;
  sidebarId: string;
  onShowSidebar: () => void;
  showSidebarRef: Ref<HTMLButtonElement>;
}

export function TopBar({
  title,
  project,
  sidebarVisible,
  isDrawer,
  sidebarId,
  onShowSidebar,
  showSidebarRef,
}: TopBarProps) {
  return (
    <header className="flex h-14 flex-none items-center gap-2.5 border-b border-line bg-surface px-5 max-wide:px-3">
      {/* The drawer covers the bar, so its button stays put for focus to return to. */}
      {(isDrawer || !sidebarVisible) && (
        <IconButton
          ref={showSidebarRef}
          icon={isDrawer ? 'menu' : 'panel'}
          label={isDrawer ? 'Open menu' : 'Show sidebar'}
          aria-expanded={sidebarVisible}
          aria-controls={sidebarId}
          onClick={onShowSidebar}
        />
      )}
      <h1 className="min-w-0 truncate text-[15px] font-semibold">{title}</h1>
      {project?.chip && (
        <Tag tone={project.chip.tone} className="px-[9px] py-[3px] text-xs max-wide:hidden">
          {project.chip.text}
        </Tag>
      )}
      {project && (project.nextStep !== null || project.runInView !== null) && (
        <div className="ml-auto flex items-center gap-2">
          {project.nextStep && <NextStepPill step={project.nextStep} />}
          {project.runInView && <RunDetailsButton run={project.runInView} />}
        </div>
      )}
    </header>
  );
}

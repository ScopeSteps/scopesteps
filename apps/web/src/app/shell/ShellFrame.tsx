import { useEffect, useId, useRef, useState } from 'react';
import { Outlet, useMatches, useNavigate } from 'react-router';

import { chatPath } from '@/app/paths';
import { ReplayBanner } from '@/features/agent-runs';
import { NewProjectModal, ProjectSettingsModal } from '@/features/projects';

import { cx } from '@/lib/cx';
import { useMediaQuery } from '@/lib/useMediaQuery';

import { usePreferences } from './preferencesContext';
import type { ProjectStatus } from './projectStatus';
import { SettingsModal } from './SettingsModal';
import { Sidebar } from './Sidebar';
import { SidebarDrawer } from './SidebarDrawer';
import { TopBar } from './TopBar';

// Matches the `wide` breakpoint in index.css: below it the sidebar is a drawer.
const DRAWER_QUERY = '(max-width: 900px)';
const APP_NAME = 'ScopeSteps';

function hasTitle(handle: unknown): handle is { title: string } {
  return (
    typeof handle === 'object' &&
    handle !== null &&
    'title' in handle &&
    typeof handle.title === 'string'
  );
}

interface ShellFrameProps {
  /** The project in view, or null on a page that belongs to no project. */
  project: ProjectStatus | null;
}

export function ShellFrame({ project }: ShellFrameProps) {
  const { preferences, updatePreferences } = usePreferences();
  const isDrawer = useMediaQuery(DRAWER_QUERY);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [projectLayer, setProjectLayer] = useState<'new' | 'settings' | null>(null);
  const navigate = useNavigate();
  const sidebarId = useId();
  const mainId = useId();
  const hideButton = useRef<HTMLButtonElement>(null);
  const showButton = useRef<HTMLButtonElement>(null);
  const toggled = useRef(false);

  const title = useMatches()
    .map((match) => match.handle)
    .findLast(hasTitle)?.title;
  const sidebarVisible = isDrawer ? drawerOpen : !preferences.sidebarCollapsed;

  // On desktop, hiding or showing the sidebar removes the button that was pressed; focus
  // follows to its counterpart instead of being dropped. The drawer returns focus by itself.
  useEffect(() => {
    if (toggled.current) {
      toggled.current = false;
      (sidebarVisible ? hideButton : showButton).current?.focus();
    }
  }, [sidebarVisible]);

  function setSidebarVisible(visible: boolean) {
    toggled.current = true;
    if (isDrawer) {
      setDrawerOpen(visible);
    } else {
      updatePreferences({ sidebarCollapsed: !visible });
    }
  }

  const sidebar = (
    <Sidebar
      id={sidebarId}
      project={project}
      isDrawer={isDrawer}
      hideRef={hideButton}
      onHide={() => {
        setSidebarVisible(false);
      }}
      onNavigate={() => {
        setDrawerOpen(false);
      }}
      onOpenSettings={() => {
        setDrawerOpen(false);
        setSettingsOpen(true);
      }}
      onNewProject={() => {
        setDrawerOpen(false);
        setProjectLayer('new');
      }}
      onOpenProjectSettings={() => {
        setDrawerOpen(false);
        setProjectLayer('settings');
      }}
    />
  );

  return (
    <div
      className={cx(
        'grid h-full grid-cols-[minmax(0,1fr)]',
        sidebarVisible && !isDrawer && 'wide:grid-cols-[248px_minmax(0,1fr)]',
      )}
    >
      <a
        href={`#${mainId}`}
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2 focus:shadow-pop"
      >
        Skip to content
      </a>
      {sidebarVisible && !isDrawer && sidebar}
      {sidebarVisible && isDrawer && (
        <SidebarDrawer
          initialFocus={hideButton}
          returnFocus={showButton}
          onClose={() => {
            setDrawerOpen(false);
          }}
        >
          {sidebar}
        </SidebarDrawer>
      )}
      <div className="flex h-full min-h-0 min-w-0 flex-col bg-bg">
        <TopBar
          title={title ?? APP_NAME}
          project={project}
          sidebarVisible={sidebarVisible}
          isDrawer={isDrawer}
          sidebarId={sidebarId}
          showSidebarRef={showButton}
          onShowSidebar={() => {
            setSidebarVisible(true);
          }}
        />
        <ReplayBanner />
        <main id={mainId} tabIndex={-1} className="min-h-0 flex-1 overflow-auto">
          {/* A page starts afresh in another project, so no state carries over from the last. */}
          <Outlet key={project?.projectId} />
        </main>
      </div>
      {settingsOpen && (
        <SettingsModal
          projectId={project?.projectId ?? null}
          onClose={() => {
            setSettingsOpen(false);
          }}
        />
      )}
      {projectLayer === 'new' && (
        <NewProjectModal
          onClose={() => {
            setProjectLayer(null);
          }}
          onDone={(projectId) => {
            setProjectLayer(null);
            void navigate(chatPath(projectId));
          }}
        />
      )}
      {projectLayer === 'settings' && project && (
        <ProjectSettingsModal
          projectId={project.projectId}
          onClose={() => {
            setProjectLayer(null);
          }}
        />
      )}
    </div>
  );
}

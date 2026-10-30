import { useState } from 'react';
import type { ReactNode } from 'react';

import { useNavigate } from 'react-router';

import { activityPath, backlogPath, changesPath, chatPath, peoplePath } from '@/app/paths';
import { PageBody } from '@/app/shell/PageBody';
import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { EmptyState } from '@/components/EmptyState';
import { Icon } from '@/components/Icon';
import { HealthStatus } from '@/features/health';
import { MyWorkView, NewProjectModal, useMyWork } from '@/features/projects';
import type { MyWork, WorkPage } from '@/features/projects';
import { describeError } from '@/lib/apiError';

const PAGE_PATHS: Record<WorkPage, (projectId: string) => string> = {
  changes: changesPath,
  backlog: backlogPath,
  chat: chatPath,
  people: peoplePath,
  activity: activityPath,
};

function pathFor(projectId: string, page: WorkPage): string {
  return PAGE_PATHS[page](projectId);
}

/** What waits for the user across their projects, and the projects themselves. */
export function HomePage() {
  const { data: work, error, refetch } = useMyWork();
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  const newProjectButton = (
    <Button
      variant="primary"
      onClick={() => {
        setCreating(true);
      }}
    >
      <Icon name="plus" size={16} />
      New project
    </Button>
  );
  return (
    <>
      <HomeContent
        work={work}
        error={error}
        newProjectButton={newProjectButton}
        onRetry={() => void refetch()}
      />
      {/* Outside the content, so it stays open when the first project changes the page. */}
      {creating && (
        <NewProjectModal
          onClose={() => {
            setCreating(false);
          }}
          onDone={(projectId) => {
            setCreating(false);
            void navigate(chatPath(projectId));
          }}
        />
      )}
    </>
  );
}

interface HomeContentProps {
  work: MyWork | undefined;
  error: Error | null;
  newProjectButton: ReactNode;
  onRetry: () => void;
}

function HomeContent({ work, error, newProjectButton, onRetry }: HomeContentProps) {
  if (error) {
    return (
      <PageBody>
        <Banner
          tone="bad"
          role="alert"
          action={
            <Button size="sm" onClick={onRetry}>
              Try again
            </Button>
          }
        >
          Could not load your projects. {describeError(error)}
        </Banner>
        <HealthStatus />
      </PageBody>
    );
  }
  if (!work) {
    return (
      <PageBody>
        <p role="status">Loading your projects…</p>
      </PageBody>
    );
  }
  if (work.projects.length === 0) {
    return (
      <EmptyState title="No projects yet" action={newProjectButton}>
        <p>Create a project to add its sources and start scoping with ScopeSteps.</p>
      </EmptyState>
    );
  }
  return (
    <PageBody>
      <MyWorkView work={work} pathFor={pathFor} newProjectButton={newProjectButton} />
    </PageBody>
  );
}

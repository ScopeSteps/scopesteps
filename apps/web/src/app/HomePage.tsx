import { useState } from 'react';
import type { ReactNode } from 'react';

import type { components } from '@scopesteps/api-client';
import { Link, Navigate, useNavigate } from 'react-router';

import { chatPath } from '@/app/paths';
import { PageBody } from '@/app/shell/PageBody';
import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { EmptyState } from '@/components/EmptyState';
import { Icon } from '@/components/Icon';
import { HealthStatus } from '@/features/health';
import { roleLabelFor } from '@/features/identity';
import { NewProjectModal, projectStatusText, useProjects } from '@/features/projects';
import { describeError } from '@/lib/apiError';

/** Sends the user to their only project, or lists their projects by name to pick one. */
export function HomePage() {
  const { data: projects, error, refetch } = useProjects();
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
        projects={projects}
        error={error}
        creating={creating}
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

type Project = components['schemas']['ProjectResponse'];

interface HomeContentProps {
  projects: Project[] | undefined;
  error: Error | null;
  creating: boolean;
  newProjectButton: ReactNode;
  onRetry: () => void;
}

function HomeContent({ projects, error, creating, newProjectButton, onRetry }: HomeContentProps) {
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
  if (!projects) {
    return (
      <PageBody>
        <p role="status">Loading your projects…</p>
      </PageBody>
    );
  }

  const [onlyProject] = projects;
  // Not while creating: the new project is listed before the user has finished with the modal.
  if (onlyProject && projects.length === 1 && !creating) {
    return <Navigate to={chatPath(onlyProject.id)} replace />;
  }
  if (projects.length === 0) {
    return (
      <EmptyState title="No projects yet" action={newProjectButton}>
        <p>Create a project to add its sources and start scoping with ScopeSteps.</p>
      </EmptyState>
    );
  }

  return (
    <PageBody>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[17px] font-semibold">Your projects</h2>
        {newProjectButton}
      </div>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {projects.map((project) => {
          const role = roleLabelFor(project.roles);
          return (
            <li key={project.id}>
              <Card>
                <Link
                  to={chatPath(project.id)}
                  className="font-semibold break-words text-accent-ink hover:underline"
                >
                  {project.name}
                </Link>
                <span className="text-xs text-subtle">
                  {projectStatusText(project.status)}
                  {role && ` · ${role}`}
                </span>
              </Card>
            </li>
          );
        })}
      </ul>
    </PageBody>
  );
}

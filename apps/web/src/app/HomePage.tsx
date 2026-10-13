import { Link, Navigate } from 'react-router';

import { backlogPath, sourcesPath } from '@/app/paths';
import { PageBody } from '@/app/shell/PageBody';
import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { EmptyState } from '@/components/EmptyState';
import { HealthStatus } from '@/features/health';
import { useCurrentUser } from '@/features/identity';
import { describeError } from '@/lib/apiError';

/**
 * Sends the user to their project. With several projects it lists them by id, the only name
 * the API gives a project so far.
 */
export function HomePage() {
  const { data: user, error, isPending, refetch } = useCurrentUser();

  if (isPending) {
    return (
      <PageBody>
        <p role="status">Loading your projects…</p>
      </PageBody>
    );
  }
  if (error) {
    return (
      <PageBody>
        <Banner
          tone="bad"
          role="alert"
          action={
            <Button size="sm" onClick={() => void refetch()}>
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

  const projectIds = [...new Set(user.memberships.map((membership) => membership.project_id))];
  const [onlyProjectId] = projectIds;
  if (onlyProjectId && projectIds.length === 1) {
    return <Navigate to={backlogPath(onlyProjectId)} replace />;
  }
  if (projectIds.length === 0) {
    return (
      <EmptyState title="No projects yet">
        <p>
          Projects you are a member of appear here. This account is not a member of any project.
        </p>
      </EmptyState>
    );
  }

  return (
    <PageBody>
      <h2 className="text-[17px] font-semibold">Your projects</h2>
      <ul className="flex flex-col gap-3">
        {projectIds.map((projectId) => (
          <li key={projectId}>
            <Card>
              <span className="font-mono text-xs break-all text-subtle tabular-nums">
                {projectId}
              </span>
              <span className="flex gap-4 font-medium text-accent-ink">
                <Link
                  to={backlogPath(projectId)}
                  aria-label={`Backlog of project ${projectId}`}
                  className="hover:underline"
                >
                  Backlog
                </Link>
                <Link
                  to={sourcesPath(projectId)}
                  aria-label={`Sources of project ${projectId}`}
                  className="hover:underline"
                >
                  Sources
                </Link>
              </span>
            </Card>
          </li>
        ))}
      </ul>
    </PageBody>
  );
}

import { Link } from 'react-router';

import { HealthStatus } from '@/features/health';
import { useCurrentUser } from '@/features/identity';

export function HomePage() {
  const { data: user } = useCurrentUser();
  const projectIds = [...new Set(user?.memberships.map((membership) => membership.project_id))];

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">ScopeSteps</h1>
      <p className="mt-2 text-gray-600">Evidence-backed backlogs with human-approved baselines.</p>
      <HealthStatus />
      {projectIds.length > 0 && (
        <nav aria-label="Projects" className="mt-6">
          <ul className="space-y-1">
            {projectIds.map((projectId) => (
              <li key={projectId}>
                <Link to={`/projects/${projectId}/sources`} className="text-blue-800 underline">
                  Sources
                </Link>
                {projectIds.length > 1 && (
                  <span className="ml-2 font-mono text-xs text-gray-600">{projectId}</span>
                )}
              </li>
            ))}
          </ul>
        </nav>
      )}
    </main>
  );
}

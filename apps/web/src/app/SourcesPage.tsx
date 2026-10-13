import { Link, useParams } from 'react-router';

import { SourcesView } from '@/features/sources';

export function SourcesPage() {
  const { projectId } = useParams();
  if (!projectId) {
    return null;
  }

  return (
    <main className="mx-auto max-w-4xl p-8">
      <nav aria-label="Project" className="flex gap-4 text-sm">
        <Link to="/" className="text-blue-800 underline">
          ← Home
        </Link>
        <Link to={`/projects/${projectId}/backlog`} className="text-blue-800 underline">
          Backlog
        </Link>
      </nav>
      <h1 className="mt-2 mb-6 text-2xl font-semibold">Sources</h1>
      <SourcesView projectId={projectId} />
    </main>
  );
}

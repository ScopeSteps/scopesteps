import { HealthStatus } from '@/features/health';

export function HomePage() {
  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">ScopeSteps</h1>
      <p className="mt-2 text-gray-600">Evidence-backed backlogs with human-approved baselines.</p>
      <HealthStatus />
    </main>
  );
}

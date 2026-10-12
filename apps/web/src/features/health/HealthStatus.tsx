import { useApiHealth } from './useApiHealth';

export function HealthStatus() {
  const { isPending, isError } = useApiHealth();

  const label = isPending ? 'Checking API…' : isError ? 'API unavailable' : 'API ready';

  return (
    <p role="status" className="mt-6 text-sm">
      {label}
    </p>
  );
}

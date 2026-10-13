import { Link } from 'react-router';

import { EmptyState } from '@/components/EmptyState';

export function NotFoundPage() {
  return (
    <EmptyState
      title="Page not found"
      action={
        <Link to="/" className="font-medium text-accent-ink hover:underline">
          Go to your projects
        </Link>
      }
    >
      <p>Nothing lives at this address. The link may be old or mistyped.</p>
    </EmptyState>
  );
}

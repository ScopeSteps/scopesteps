import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { EmptyState } from '@/components/EmptyState';
import { describeError } from '@/lib/apiError';
import { formatWhen } from '@/lib/formatWhen';

import type { ActivityEvent } from './types';
import { useActivity } from './useActivity';

/** Who acted, as the server recorded it: the agent, or the user's name at the time. */
function actorName(event: ActivityEvent): string {
  if (event.actor.kind === 'agent') {
    return 'Agent';
  }
  return event.actor.display_name ?? 'Unknown user';
}

export function ActivityView({ projectId }: { projectId: string }) {
  const { data, error, isPending, refetch, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useActivity(projectId);
  const events = data?.pages.flatMap((page) => page.events) ?? [];

  if (isPending) {
    return <p role="status">Loading activity…</p>;
  }
  if (error && events.length === 0) {
    return (
      <Banner
        tone="bad"
        role="alert"
        action={
          <Button size="sm" onClick={() => void refetch()}>
            Try again
          </Button>
        }
      >
        Could not load the activity log. {describeError(error)}
      </Banner>
    );
  }
  if (events.length === 0) {
    return (
      <EmptyState title="No activity yet">
        Adding sources, running the agent and answering its questions appear here, with who did them
        and when.
      </EmptyState>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-muted">Every answer, decision, edit and approval, newest first.</p>
      <div className="overflow-hidden rounded-xl border border-line bg-surface">
        <ul aria-label="Activity">
          {events.map((event) => (
            <li
              key={event.id}
              className="grid grid-cols-[110px_130px_minmax(0,1fr)] gap-3 border-t border-line px-3.5 py-[11px] text-[13px] first:border-t-0 max-sm:grid-cols-1 max-sm:gap-0.5"
            >
              <time dateTime={event.occurred_at} className="font-mono text-subtle tabular-nums">
                {formatWhen(event.occurred_at)}
              </time>
              <span className="font-semibold">{actorName(event)}</span>
              <span>{event.summary}</span>
            </li>
          ))}
        </ul>
      </div>
      {error && (
        <Banner tone="bad" role="alert">
          Could not load more activity. {describeError(error)}
        </Banner>
      )}
      {hasNextPage && (
        <Button onClick={() => void fetchNextPage()} disabled={isFetchingNextPage}>
          {isFetchingNextPage ? 'Loading…' : 'Show older activity'}
        </Button>
      )}
    </div>
  );
}

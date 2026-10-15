import type { ReactNode } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { describeError } from '@/lib/apiError';

import { ChangeRequestCard } from './ChangeRequestCard';
import type { ChangeRequestLinks } from './ChangeRequestCard';
import type { ChangeRequest } from './types';
import { useChangeRequests } from './useChangeRequests';

interface ChangeRequestListProps extends ChangeRequestLinks {
  projectId: string;
  /** Shown when there is no request yet. */
  empty: ReactNode;
  /** The candidate's scope conflict, if any, for a request with a candidate. */
  renderConflict: (request: ChangeRequest) => ReactNode;
}

/** Every change request of the project, newest first, with older ones on demand. */
export function ChangeRequestList({
  projectId,
  empty,
  renderConflict,
  versionHref,
  chatHref,
}: ChangeRequestListProps) {
  const query = useChangeRequests(projectId);

  if (query.isPending) {
    return (
      <p role="status" className="text-subtle">
        Loading the change requests…
      </p>
    );
  }
  if (query.isError && query.requests.length === 0) {
    return (
      <Banner
        tone="bad"
        role="alert"
        action={
          <Button size="sm" onClick={() => void query.refetch()}>
            Try again
          </Button>
        }
      >
        Could not load the change requests. {describeError(query.error)}
      </Banner>
    );
  }
  if (query.requests.length === 0) {
    return empty;
  }
  return (
    <section aria-labelledby="change-requests-heading" className="flex flex-col gap-3">
      <h2 id="change-requests-heading" className="text-[17px] font-semibold">
        Requests
      </h2>
      {query.requests.map((request) => (
        <ChangeRequestCard
          key={request.id}
          request={request}
          conflict={request.candidate_version_id ? renderConflict(request) : null}
          versionHref={versionHref}
          chatHref={chatHref}
        />
      ))}
      {query.isFetchNextPageError && (
        <p role="alert" className="text-[13px] text-bad-ink">
          Older requests could not be loaded. {describeError(query.error)}
        </p>
      )}
      {query.hasNextPage && (
        <div>
          <Button
            size="sm"
            variant="ghost"
            disabled={query.isFetchingNextPage}
            onClick={() => void query.fetchNextPage()}
          >
            {query.isFetchingNextPage ? 'Loading older requests…' : 'Load older requests'}
          </Button>
        </div>
      )}
    </section>
  );
}

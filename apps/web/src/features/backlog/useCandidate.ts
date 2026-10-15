import { useChangeRequest, useChangeSet } from '@/features/change-control';

import { isCandidate } from './candidate';
import type { BacklogVersion } from './types';

/**
 * A candidate's change set and the request that proposed it; nothing for any other version.
 * `decided` also loads them once the candidate was approved or rejected, for a caller that knows
 * the version came from a change request.
 */
export function useCandidate(version: BacklogVersion | undefined, { decided = false } = {}) {
  const proposed =
    version !== undefined &&
    (isCandidate(version) ||
      (decided && (version.state === 'approved' || version.state === 'rejected')));
  const changeSet = useChangeSet(proposed ? version.id : null);
  const request = useChangeRequest(changeSet.data?.change_request_id ?? null);
  return { changeSet, request };
}

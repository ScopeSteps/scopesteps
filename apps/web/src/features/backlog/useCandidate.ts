import { useChangeRequest, useChangeSet } from '@/features/change-control';

import { isCandidate } from './candidate';
import type { BacklogVersion } from './types';

/** A candidate's change set and the request that proposed it; nothing for any other version. */
export function useCandidate(version: BacklogVersion | undefined) {
  const changeSet = useChangeSet(version && isCandidate(version) ? version.id : null);
  const request = useChangeRequest(changeSet.data?.change_request_id ?? null);
  return { changeSet, request };
}

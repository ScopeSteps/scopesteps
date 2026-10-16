import { Link } from 'react-router';

import { Banner } from '@/components/Banner';
import { useChangeSet } from '@/features/change-control';
import { useReviewerName } from '@/features/identity';

import { useBacklogVersion } from './useBacklogVersion';

interface ScopeConflictBannerProps {
  projectId: string;
  versionId: string;
  /** Where the backlog opens the evidence sheet on one of the candidate's decisions. */
  evidenceHref: (decisionId: string) => string;
}

/**
 * The earlier exclusions or decisions a change candidate would reverse, and whether an approver
 * has decided each one. Nothing when the candidate reverses nothing.
 */
export function ScopeConflictBanner({
  projectId,
  versionId,
  evidenceHref,
}: ScopeConflictBannerProps) {
  const { data: changeSet } = useChangeSet(versionId);
  const { data: version } = useBacklogVersion(projectId, versionId);
  const reviewerName = useReviewerName(projectId);
  if (!changeSet || changeSet.scope_decisions.length === 0) {
    return null;
  }
  return (
    <Banner tone="warn">
      <ul className="m-0 flex list-none flex-col gap-1 p-0">
        {changeSet.scope_decisions.map((reversal) => {
          const decision = version?.decisions.find(
            (candidate) => candidate.id === reversal.decision_id,
          );
          const what = reversal.reverses === 'exclusion' ? 'an exclusion' : 'an earlier decision';
          let state = 'Waiting for a scope decision.';
          if (decision?.answer === 'reverse') {
            // Choosing to reverse is not the change's outcome: a rejection still keeps the scope.
            state =
              version?.state === 'rejected'
                ? `Reversal chosen by ${reviewerName(decision.decided_by)}, but the change was rejected, so nothing was reversed.`
                : `Reversal approved by ${reviewerName(decision.decided_by)}.`;
          } else if (decision?.answer === 'keep') {
            state = `${reversal.reverses === 'exclusion' ? 'Exclusion' : 'Decision'} kept by ${reviewerName(decision.decided_by)}.`;
          }
          return (
            <li key={reversal.decision_id}>
              Reverses {what}: {reversal.summary} <strong className="font-semibold">{state}</strong>{' '}
              <Link
                className="text-accent-ink underline"
                to={evidenceHref(reversal.decision_id)}
                aria-label={`Evidence for: ${reversal.summary}`}
              >
                Evidence
              </Link>
            </li>
          );
        })}
      </ul>
    </Banner>
  );
}

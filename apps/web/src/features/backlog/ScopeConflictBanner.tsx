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
          const ruledOut = reversal.reverses === 'exclusion';
          const what = ruledOut
            ? 'Brings back something that was ruled out'
            : 'Changes an earlier decision';
          let state = 'Waiting for an Approver to decide.';
          if (decision?.answer === 'reverse') {
            // Saying yes is not the change's outcome: a rejection still keeps the earlier scope.
            const who = reviewerName(decision.decided_by);
            state =
              version?.state === 'rejected'
                ? `${who} said yes, but the change was rejected, so nothing changed.`
                : `${who} said yes.`;
          } else if (decision?.answer === 'keep') {
            state = `${ruledOut ? 'Kept out' : 'Kept'} by ${reviewerName(decision.decided_by)}.`;
          }
          return (
            <li key={reversal.decision_id}>
              {what}: {reversal.summary} <strong className="font-semibold">{state}</strong>{' '}
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

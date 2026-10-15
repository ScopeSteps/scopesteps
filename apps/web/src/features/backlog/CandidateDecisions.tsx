import { Banner } from '@/components/Banner';
import { DiffTag } from '@/components/DiffTag';
import { changeRequestName } from '@/features/change-control';
import type { ChangeRequest } from '@/features/change-control';

import { diffByItem } from './candidate';
import { ScopeDecisionCard } from './ScopeDecisionCard';
import { useBacklogVersion } from './useBacklogVersion';
import { useCandidate } from './useCandidate';

/** What became of the request once an approver decided its candidate; nothing before. */
function outcome(request: ChangeRequest | undefined): string | null {
  if (!request) {
    return null;
  }
  const name = changeRequestName(request.number);
  const base =
    request.base_version_number === null
      ? 'the baseline'
      : `v${String(request.base_version_number)}`;
  const next =
    request.base_version_number === null
      ? 'the new baseline'
      : `v${String(request.base_version_number + 1)}`;
  switch (request.status) {
    case 'approved':
      return `${name} approved: the candidate is now ${next}, the current baseline. ${base} stays in history, unchanged.`;
    case 'rejected':
      return `${name} rejected: ${base} is still the current baseline, unchanged.`;
    default:
      return null;
  }
}

interface CandidateDecisionsProps {
  projectId: string;
  versionId: string;
  /** Opens the evidence behind one of the candidate's decisions. */
  onShowEvidence: (decisionId: string) => void;
}

/**
 * What a change candidate proposes, counted from the server's comparison, and the scope decisions
 * it needs, for the chat that follows its change run, and the approver's outcome once decided.
 */
export function CandidateDecisions({
  projectId,
  versionId,
  onShowEvidence,
}: CandidateDecisionsProps) {
  const { data: version } = useBacklogVersion(projectId, versionId);
  const { changeSet, request } = useCandidate(version, { decided: true });
  const decided = outcome(request.data);
  if (!version || !changeSet.data) {
    return changeSet.isError ? (
      <Banner tone="bad" role="alert">
        Could not load what this candidate changes.
      </Banner>
    ) : null;
  }
  const kinds = [...diffByItem(changeSet.data).values()];
  const count = (kind: string) => kinds.filter((candidate) => candidate === kind).length;
  return (
    <>
      <ul aria-label="Proposed changes" className="flex flex-wrap gap-3 text-[13px]">
        <li className="flex items-center gap-1.5">
          <DiffTag kind="added" /> {count('added')}
        </li>
        <li className="flex items-center gap-1.5">
          <DiffTag kind="changed" /> {count('changed')}
        </li>
        <li className="flex items-center gap-1.5">
          <DiffTag kind="removed" /> {count('removed')}
        </li>
      </ul>
      {version.decisions
        .filter((decision) => decision.kind === 'scope_reversal')
        .map((decision) => (
          <ScopeDecisionCard
            key={decision.id}
            projectId={projectId}
            version={version}
            decision={decision}
            reversal={changeSet.data.scope_decisions.find(
              (reversal) => reversal.decision_id === decision.id,
            )}
            onShowEvidence={onShowEvidence}
          />
        ))}
      {decided && <p className="text-sm font-semibold">{decided}</p>}
    </>
  );
}

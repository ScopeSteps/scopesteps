import { Banner } from '@/components/Banner';
import { DiffTag } from '@/components/DiffTag';

import { diffByItem } from './candidate';
import { ScopeDecisionCard } from './ScopeDecisionCard';
import { useBacklogVersion } from './useBacklogVersion';
import { useCandidate } from './useCandidate';

interface CandidateDecisionsProps {
  projectId: string;
  versionId: string;
  /** Opens the evidence behind one of the candidate's decisions. */
  onShowEvidence: (decisionId: string) => void;
}

/**
 * What a change candidate proposes, counted from the server's comparison, and the scope decisions
 * it needs, for the chat that follows its change run.
 */
export function CandidateDecisions({
  projectId,
  versionId,
  onShowEvidence,
}: CandidateDecisionsProps) {
  const { data: version } = useBacklogVersion(projectId, versionId);
  const { changeSet } = useCandidate(version);
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
    </>
  );
}

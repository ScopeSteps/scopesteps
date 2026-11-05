import { useId } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Tag } from '@/components/Tag';
import type { ScopeReversal } from '@/features/change-control';
import { roleName, useCan, useProjectRole, useReviewerName } from '@/features/identity';
import { SourceCitationChip } from '@/features/sources';
import { describeError } from '@/lib/apiError';

import type { BacklogVersion, Decision, EvidenceRef } from './types';
import { isScopeStale, useScopeDecision } from './useScopeDecision';

interface ScopeDecisionCardProps {
  projectId: string;
  /** The candidate in review the decision belongs to. */
  version: BacklogVersion;
  decision: Decision;
  /** What the decision would take back, from the change set; absent while it loads. */
  reversal: ScopeReversal | undefined;
  onShowEvidence: (decisionId: string) => void;
}

/** The card's words for what the change would undo: something ruled out, or an earlier decision. */
interface Wording {
  question: string;
  earlier: string;
  why: string;
  yes: string;
  no: string;
  yesTag: string;
  noTag: string;
  yesDone: string;
  noDone: string;
}

const RULED_OUT: Wording = {
  question: 'Bring this back into scope?',
  earlier: 'Ruled out earlier',
  why: 'Why it was ruled out',
  yes: 'Yes, bring it back',
  no: 'No, keep it out',
  yesTag: 'Brought back',
  noTag: 'Kept out',
  yesDone: 'Brought back into scope',
  noDone: 'Kept out of scope',
};

const EARLIER_DECISION: Wording = {
  question: 'Change an earlier decision?',
  earlier: 'Decided earlier',
  why: 'Why it was decided',
  yes: 'Yes, change it',
  no: 'No, keep it',
  yesTag: 'Changed',
  noTag: 'Kept',
  yesDone: 'Changed the earlier decision',
  noDone: 'Kept the earlier decision',
};

function wordingFor(reversal: ScopeReversal | undefined): Wording {
  return reversal?.reverses === 'decision' ? EARLIER_DECISION : RULED_OUT;
}

/**
 * A proposed version's scope decision: bring back work that was ruled out, or change an earlier
 * decision, with the quotes behind the earlier scope and the change request. Only an approver
 * answers it; everyone else sees who must decide.
 */
export function ScopeDecisionCard({
  projectId,
  version,
  decision,
  reversal,
  onShowEvidence,
}: ScopeDecisionCardProps) {
  const headingId = useId();
  const canApprove = useCan(projectId, 'decide_versions');
  const heldRole = useProjectRole(projectId);
  const reviewerName = useReviewerName(projectId);
  const command = useScopeDecision(projectId, version);
  const words = wordingFor(reversal);
  // The stored subject reads "Reverse: <summary>"; the change set's summary is the plain one.
  const summary = reversal?.summary ?? decision.subject.replace(/^Reverse: /, '');
  const stale = isScopeStale(command.error) ? command.error : null;
  const failure = command.error && !stale ? command.error : null;

  const quotes = (references: EvidenceRef[], label: string) =>
    references.length > 0 && (
      <div className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-subtle">{label}</span>
        <ul aria-label={label} className="m-0 flex list-none flex-col gap-2 p-0">
          {references.map((reference) => (
            <li key={`${reference.block_id}-${reference.quote ?? ''}`}>
              <blockquote className="m-0 rounded-lg border border-line bg-surface px-3 py-2 text-sm">
                {reference.quote ? `“${reference.quote}” ` : 'The cited paragraph '}
                <SourceCitationChip
                  projectId={projectId}
                  sourceVersionId={reference.source_version_id}
                  blockId={reference.block_id}
                  about={summary}
                  onOpen={() => {
                    onShowEvidence(decision.id);
                  }}
                />
              </blockquote>
            </li>
          ))}
        </ul>
      </div>
    );
  // The earlier scope's own evidence is copied from the baseline; the change request's
  // passages are the ones that conflict with it.
  const evidence = (
    <>
      {quotes(
        decision.evidence.filter((reference) => reference.relationship !== 'conflicting'),
        words.why,
      )}
      {quotes(
        decision.evidence.filter((reference) => reference.relationship === 'conflicting'),
        'What the change request says',
      )}
    </>
  );

  if (decision.status === 'answered') {
    const reversed = decision.answer === 'reverse';
    return (
      <Card role="article" aria-labelledby={headingId}>
        <div className="flex flex-wrap items-center gap-2">
          <Tag tone={reversed ? 'ok' : 'neutral'}>{reversed ? words.yesTag : words.noTag}</Tag>
          <span id={headingId} className="text-xs text-subtle">
            Scope decision
          </span>
        </div>
        <strong className="font-semibold">
          {reversed ? words.yesDone : words.noDone}: {summary}
        </strong>
        {evidence}
        <span className="text-xs text-subtle">
          Decided by {reviewerName(decision.decided_by)}. Saved as evidence.
        </span>
      </Card>
    );
  }

  const role = heldRole ? roleName(heldRole) : null;
  const open = version.state === 'in_review';

  return (
    <Card role="article" aria-labelledby={headingId} tone={open ? 'decide' : 'default'}>
      <strong id={headingId} className="font-semibold">
        {words.question}
      </strong>
      <p>
        <span className="font-semibold">{words.earlier}:</span> {summary}
      </p>
      {evidence}
      {!open ? (
        <span className="text-xs text-subtle">
          This decision closed when the change was approved or rejected.
        </span>
      ) : canApprove ? (
        <>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="primary"
              disabled={command.isPending || stale !== null}
              onClick={() => {
                command.decide(decision.id, 'reverse');
              }}
            >
              {command.isPending && command.outcome === 'reverse' ? 'Saving…' : words.yes}
            </Button>
            <Button
              size="sm"
              disabled={command.isPending || stale !== null}
              onClick={() => {
                command.decide(decision.id, 'keep');
              }}
            >
              {command.isPending && command.outcome === 'keep' ? 'Saving…' : words.no}
            </Button>
          </div>
          <span className="text-xs text-subtle">
            Only an Approver can decide this. The agent never decides scope.
          </span>
        </>
      ) : (
        <span className="text-xs text-subtle">
          Waiting for an Approver to decide.
          {role && ` Your role (${role}) can’t decide scope.`}
        </span>
      )}
      {stale && (
        <Banner
          tone="bad"
          role="alert"
          action={
            <Button size="sm" onClick={() => void command.reload()}>
              Reload
            </Button>
          }
        >
          {stale.code === 'VERSION_NOT_IN_REVIEW'
            ? 'This proposed version was approved or rejected in the meantime.'
            : 'Someone else changed this proposed version after you opened it.'}{' '}
          Your choice was not saved. Reload to see the latest version.
        </Banner>
      )}
      {failure && (
        <Banner tone="bad" role="alert">
          Your choice was not saved. {describeError(failure)}
        </Banner>
      )}
    </Card>
  );
}

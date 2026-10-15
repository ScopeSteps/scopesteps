import { useId } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Tag } from '@/components/Tag';
import type { ScopeReversal } from '@/features/change-control';
import { roleLabelFor, useCanApprove, useCurrentUser, useReviewerName } from '@/features/identity';
import { SourceCitationChip } from '@/features/sources';
import { describeError } from '@/lib/apiError';

import type { BacklogVersion, Decision } from './types';
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

function subjectOf(reversal: ScopeReversal | undefined): string {
  if (!reversal) {
    return 'earlier scope';
  }
  return reversal.reverses === 'exclusion' ? 'the exclusion' : 'the earlier decision';
}

/**
 * A candidate's scope decision: work an earlier exclusion or decision ruled out, with the quoted
 * evidence for it. Only an approver answers it; everyone else sees who must decide.
 */
export function ScopeDecisionCard({
  projectId,
  version,
  decision,
  reversal,
  onShowEvidence,
}: ScopeDecisionCardProps) {
  const headingId = useId();
  const canApprove = useCanApprove(projectId);
  const { data: user } = useCurrentUser();
  const reviewerName = useReviewerName(projectId);
  const command = useScopeDecision(projectId, version);
  const summary = reversal?.summary ?? decision.subject;
  const stale = isScopeStale(command.error) ? command.error : null;
  const failure = command.error && !stale ? command.error : null;

  const evidence = decision.evidence.length > 0 && (
    <ul
      aria-label="Evidence for the earlier scope"
      className="m-0 flex list-none flex-col gap-2 p-0"
    >
      {decision.evidence.map((reference) => (
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
  );

  if (decision.status === 'answered') {
    const reversed = decision.answer === 'reverse';
    return (
      <Card role="article" aria-labelledby={headingId}>
        <div className="flex flex-wrap items-center gap-2">
          <Tag tone={reversed ? 'ok' : 'neutral'}>{reversed ? 'Reversed' : 'Kept'}</Tag>
          <span id={headingId} className="text-xs text-subtle">
            Scope decision
          </span>
        </div>
        <strong className="font-semibold">
          {reversed
            ? `Reversed ${subjectOf(reversal)}: ${summary}`
            : `Kept ${subjectOf(reversal)}: ${summary}`}
        </strong>
        {evidence}
        <span className="text-xs text-subtle">
          Decided by {reviewerName(decision.decided_by)}. Saved as evidence.
        </span>
      </Card>
    );
  }

  const roles =
    user?.memberships
      .filter((membership) => membership.project_id === projectId)
      .map((membership) => membership.role) ?? [];
  const role = roleLabelFor(roles);
  const open = version.state === 'in_review';

  return (
    <Card role="article" aria-labelledby={headingId} tone={open ? 'decide' : 'default'}>
      <strong id={headingId} className="font-semibold">
        Decision needed: reverse {subjectOf(reversal)}?
      </strong>
      <p>{summary}</p>
      {evidence}
      {!open ? (
        <span className="text-xs text-subtle">
          This decision closed when the change was resolved.
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
              {command.isPending && command.outcome === 'reverse' ? 'Saving…' : 'Yes, reverse it'}
            </Button>
            <Button
              size="sm"
              disabled={command.isPending || stale !== null}
              onClick={() => {
                command.decide(decision.id, 'keep');
              }}
            >
              {command.isPending && command.outcome === 'keep' ? 'Saving…' : 'No, keep it'}
            </Button>
          </div>
          <span className="text-xs text-subtle">
            Only a Product owner can make this call. The agent won’t.
          </span>
        </>
      ) : (
        <span className="text-xs text-subtle">
          Waiting for a Product owner.
          {role && ` Your role (${role}) can’t make scope decisions.`}
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
            ? 'This candidate was approved or rejected meanwhile.'
            : 'Someone else changed this candidate after you opened it.'}{' '}
          Your decision was not saved. Reload to see the latest revision.
        </Banner>
      )}
      {failure && (
        <Banner tone="bad" role="alert">
          The decision was not saved. {describeError(failure)}
        </Banner>
      )}
    </Card>
  );
}

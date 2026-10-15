import { SideSheet } from '@/components/SideSheet';
import { Tag } from '@/components/Tag';
import { useReviewerName } from '@/features/identity';
import { SourcePassage } from '@/features/sources';

import { decisionLabel, ORIGINS } from './types';
import type { BacklogVersion, ClaimOrigin, ClaimRef, Decision, EvidenceRef } from './types';

interface EvidenceSheetProps {
  version: BacklogVersion;
  claim: ClaimRef;
  onClose: () => void;
}

interface Claim {
  kind: string;
  text: string;
  origin?: ClaimOrigin;
  evidence: EvidenceRef[];
  /** Reviewer decisions shown with the claim: the ones confirming it, or the decision itself. */
  decisions: Decision[];
}

function findClaim(version: BacklogVersion, claim: ClaimRef): Claim | null {
  switch (claim.type) {
    case 'criterion': {
      const criterion = version.items
        .flatMap((item) => item.criteria)
        .find((candidate) => candidate.id === claim.id);
      return criterion
        ? {
            kind: 'Acceptance criterion',
            text: criterion.text,
            origin: criterion.origin,
            evidence: criterion.evidence,
            decisions: version.decisions.filter((decision) =>
              criterion.confirmed_by.includes(decision.id),
            ),
          }
        : null;
    }
    case 'decision': {
      const decision = version.decisions.find((candidate) => candidate.id === claim.id);
      return decision
        ? {
            kind: decisionLabel(decision),
            text: decision.subject,
            evidence: [],
            decisions: [decision],
          }
        : null;
    }
    case 'scope': {
      const note = version.out_of_scope[claim.index];
      return note
        ? {
            kind: note.kind === 'excluded' ? 'Excluded by the sources' : 'Suggested, not committed',
            text: note.summary,
            evidence: note.evidence,
            decisions: [],
          }
        : null;
    }
  }
}

/** Everything behind one claim in the backlog: its cited passages and the reviewers' answers. */
export function EvidenceSheet({ version, claim, onClose }: EvidenceSheetProps) {
  const reviewerName = useReviewerName(version.project_id);
  const found = findClaim(version, claim);

  function passages(evidence: EvidenceRef[]) {
    return (
      <ul className="m-0 flex list-none flex-col gap-4 p-0">
        {evidence.map((reference) => (
          <li
            key={`${reference.block_id}-${reference.quote ?? ''}`}
            className="flex flex-col gap-1.5"
          >
            {reference.relationship === 'conflicting' && (
              <Tag tone="bad" className="self-start">
                Conflicting passage
              </Tag>
            )}
            <SourcePassage
              projectId={version.project_id}
              sourceVersionId={reference.source_version_id}
              blockId={reference.block_id}
              quote={reference.quote}
            />
          </li>
        ))}
      </ul>
    );
  }

  return (
    <SideSheet title="Evidence" onClose={onClose}>
      {!found ? (
        <p role="alert" className="text-[13px] text-bad-ink">
          This link does not match anything in this backlog version.
        </p>
      ) : (
        <>
          <span className="text-xs text-subtle">{found.kind}</span>
          <p className="font-medium">{found.text}</p>
          {found.origin && (
            <Tag tone={ORIGINS[found.origin].tone} className="self-start">
              {ORIGINS[found.origin].label}
            </Tag>
          )}
          {found.origin === 'proposed' && (
            <p className="text-[13px]">
              The agent added this detail. No source or reviewer states it, so it needs your review
              before the story can be approved.
            </p>
          )}

          {found.evidence.length > 0 && (
            <section aria-labelledby="evidence-sources-heading" className="flex flex-col gap-2">
              <h3 id="evidence-sources-heading" className="text-[13px] font-semibold">
                Source passages
              </h3>
              {passages(found.evidence)}
            </section>
          )}

          {found.decisions.map((decision) => (
            <section
              key={decision.id}
              aria-label={`Reviewer decision: ${decision.subject}`}
              className="flex flex-col gap-2"
            >
              <h3 className="text-[13px] font-semibold">
                {decision.status === 'answered' ? 'Reviewer answer' : 'Unresolved decision'}
              </h3>
              <p className="text-[13px]">{decision.question}</p>
              {decision.status === 'answered' && (
                <figure className="m-0 flex flex-col gap-1.5">
                  <blockquote className="m-0 rounded-[10px] border border-line bg-surface-2 px-3.5 py-3 text-[15px] leading-[1.55] whitespace-pre-wrap">
                    {decision.answer}
                  </blockquote>
                  <figcaption className="text-xs text-subtle">
                    Answered by {reviewerName(decision.decided_by)}
                    {decision.decided_at && (
                      <>
                        {' · '}
                        <time dateTime={decision.decided_at}>
                          {new Date(decision.decided_at).toLocaleString()}
                        </time>
                      </>
                    )}
                  </figcaption>
                </figure>
              )}
              {decision.status === 'skipped' && (
                <p className="text-[13px]">
                  Skipped by {reviewerName(decision.decided_by)}. No answer was assumed.
                </p>
              )}
              {decision.evidence.length > 0 && (
                <>
                  <p className="text-xs text-subtle">What the sources say about it</p>
                  {passages(decision.evidence)}
                </>
              )}
            </section>
          ))}
          <p className="text-xs text-subtle">
            A citation shows where a detail came from. Whether it’s interpreted correctly is your
            call.
          </p>
        </>
      )}
    </SideSheet>
  );
}

import { useEffect, useRef } from 'react';

import { useReviewerName } from '@/features/identity';
import { SourcePassage } from '@/features/sources';

import { OriginBadge } from './OriginBadge';
import { decisionLabel } from './types';
import type { BacklogVersion, ClaimOrigin, ClaimRef, Decision, EvidenceRef } from './types';

interface EvidenceDrawerProps {
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

export function EvidenceDrawer({ version, claim, onClose }: EvidenceDrawerProps) {
  const reviewerName = useReviewerName();
  const heading = useRef<HTMLHeadingElement>(null);
  const found = findClaim(version, claim);
  const claimKey = claim.type === 'scope' ? `scope:${String(claim.index)}` : claim.id;

  // Move focus into the drawer when it opens or changes claim, as a dialog would.
  useEffect(() => {
    heading.current?.focus();
  }, [claimKey]);

  function passages(evidence: EvidenceRef[]) {
    return (
      <ul className="mt-2 space-y-3">
        {evidence.map((reference) => (
          <li key={`${reference.block_id}-${reference.quote ?? ''}`}>
            {reference.relationship === 'conflicting' && (
              <p className="mb-1 text-xs font-semibold text-red-900">Conflicting passage</p>
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
    <aside
      aria-labelledby="evidence-heading"
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          onClose();
        }
      }}
      className="fixed inset-y-0 right-0 z-10 w-full max-w-md overflow-y-auto border-l border-gray-400 bg-white p-5 shadow-xl"
    >
      <div className="flex items-start justify-between gap-4">
        <h2 id="evidence-heading" ref={heading} tabIndex={-1} className="text-lg font-semibold">
          Evidence
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-gray-500 px-2 py-1 text-sm hover:bg-gray-100 focus-visible:outline-2 focus-visible:outline-blue-700"
        >
          Close evidence
        </button>
      </div>

      {!found ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          This link does not match anything in this backlog version.
        </p>
      ) : (
        <>
          <p className="mt-3 text-xs font-medium text-gray-700">{found.kind}</p>
          <p className="mt-1 font-medium">{found.text}</p>
          {found.origin && (
            <p className="mt-2">
              <OriginBadge origin={found.origin} />
            </p>
          )}
          {found.origin === 'proposed' && (
            <p className="mt-2 text-sm">
              The AI added this detail. No source or reviewer states it, so it needs your review
              before the story can be approved.
            </p>
          )}

          {found.evidence.length > 0 && (
            <section aria-labelledby="evidence-sources-heading" className="mt-4">
              <h3 id="evidence-sources-heading" className="text-sm font-semibold">
                Source passages
              </h3>
              {passages(found.evidence)}
            </section>
          )}

          {found.decisions.map((decision) => (
            <section
              key={decision.id}
              aria-label={`Reviewer decision: ${decision.subject}`}
              className="mt-4"
            >
              <h3 className="text-sm font-semibold">
                {decision.status === 'answered' ? 'Reviewer answer' : 'Unresolved decision'}
              </h3>
              <p className="mt-1 text-sm">{decision.question}</p>
              {decision.status === 'answered' && (
                <p className="mt-2 rounded bg-blue-50 p-2 text-sm">
                  <q className="whitespace-pre-wrap">{decision.answer}</q>
                  <span className="mt-1 block text-xs text-gray-700">
                    Answered by {reviewerName(decision.decided_by)}
                    {decision.decided_at && (
                      <>
                        {' on '}
                        <time dateTime={decision.decided_at}>
                          {new Date(decision.decided_at).toLocaleString()}
                        </time>
                      </>
                    )}
                  </span>
                </p>
              )}
              {decision.status === 'skipped' && (
                <p className="mt-2 text-sm">
                  Skipped by {reviewerName(decision.decided_by)}. No answer was assumed.
                </p>
              )}
              {decision.evidence.length > 0 && (
                <>
                  <p className="mt-3 text-xs font-medium text-gray-700">
                    What the sources say about it
                  </p>
                  {passages(decision.evidence)}
                </>
              )}
            </section>
          ))}
        </>
      )}
    </aside>
  );
}

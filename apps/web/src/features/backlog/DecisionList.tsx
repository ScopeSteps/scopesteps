import { useReviewerName } from '@/features/identity';

import { EvidenceButton } from './EvidenceButton';
import { decisionLabel } from './types';
import type { BacklogItem, ClaimRef, Decision } from './types';

interface DecisionListProps {
  decisions: Decision[];
  items: BacklogItem[];
  onShowEvidence: (claim: ClaimRef) => void;
}

export function DecisionList({ decisions, items, onShowEvidence }: DecisionListProps) {
  const reviewerName = useReviewerName();
  const titles = new Map(items.map((item) => [item.id, item.title]));
  const open = decisions.filter((decision) => decision.status !== 'answered');
  const answered = decisions.filter((decision) => decision.status === 'answered');

  function affected(decision: Decision): string {
    const names = decision.affected_item_ids.map((id) => titles.get(id) ?? id);
    return names.length > 0 ? names.join('; ') : 'no story yet';
  }

  return (
    <>
      <section aria-labelledby="open-decisions-heading">
        <h3 id="open-decisions-heading" className="font-semibold">
          Open decisions ({open.length})
        </h3>
        {open.length === 0 ? (
          <p className="mt-1 text-sm text-muted">Nothing is waiting for a decision.</p>
        ) : (
          <ul className="mt-2 space-y-3">
            {open.map((decision) => (
              <li key={decision.id} className="rounded border border-bad-line p-3 text-sm">
                <p className="text-xs font-semibold text-bad-ink">{decisionLabel(decision)}</p>
                <p className="mt-1 font-semibold">{decision.subject}</p>
                <p className="mt-1">{decision.question}</p>
                <p className="mt-1 text-muted">
                  <span className="font-medium">Why it matters:</span> {decision.why_it_matters}
                </p>
                <p className="mt-1">
                  <span className="font-medium">Blocks:</span> {affected(decision)}
                </p>
                {decision.status === 'skipped' && (
                  <p className="mt-1 text-muted">
                    Skipped by {reviewerName(decision.decided_by)}. No answer was assumed.
                  </p>
                )}
                <p className="mt-1">
                  <EvidenceButton
                    about={decision.subject}
                    count={decision.evidence.length}
                    onShow={() => {
                      onShowEvidence({ type: 'decision', id: decision.id });
                    }}
                  />
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      {answered.length > 0 && (
        <section aria-labelledby="answered-decisions-heading">
          <h3 id="answered-decisions-heading" className="font-semibold">
            Answered by a reviewer ({answered.length})
          </h3>
          <ul className="mt-2 space-y-3">
            {answered.map((decision) => (
              <li key={decision.id} className="rounded border border-accent p-3 text-sm">
                <p className="font-semibold">{decision.subject}</p>
                <p className="mt-1">{decision.question}</p>
                <p className="mt-1">
                  <span className="font-medium">
                    Answer by {reviewerName(decision.decided_by)}:
                  </span>{' '}
                  <span className="whitespace-pre-wrap">{decision.answer}</span>
                </p>
                <p className="mt-1">
                  <span className="font-medium">Confirms:</span> {affected(decision)}
                </p>
                <p className="mt-1">
                  <EvidenceButton
                    about={decision.subject}
                    count={decision.evidence.length}
                    onShow={() => {
                      onShowEvidence({ type: 'decision', id: decision.id });
                    }}
                  />
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

import { Tag } from '@/components/Tag';
import type { TagTone } from '@/components/Tag';
import { useReviewerName } from '@/features/identity';
import { SourceCitationChip } from '@/features/sources';

import { DecisionAnswer } from './DecisionAnswer';
import { errorFor, isLocked, isSaving } from './draftControls';
import type { DraftControls } from './draftControls';
import { decisionLabel } from './types';
import type { BacklogItem, ClaimRef, Decision } from './types';

interface DecisionRowsProps {
  projectId: string;
  decisions: Decision[];
  items: BacklogItem[];
  onShowEvidence: (claim: ClaimRef) => void;
  /** The draft's controls, or null when the version or the reader's role is read-only. */
  draft: DraftControls | null;
}

function tone(decision: Decision): TagTone {
  if (decision.status === 'answered') {
    return 'ok';
  }
  return decision.status === 'skipped' ? 'bad' : 'warn';
}

/** The decisions the draft depends on: answered, skipped or still open. */
export function DecisionRows({
  projectId,
  decisions,
  items,
  onShowEvidence,
  draft,
}: DecisionRowsProps) {
  const reviewerName = useReviewerName();
  const titles = new Map(items.map((item) => [item.id, item.title]));

  return (
    <ul
      aria-label="Decisions"
      className="m-0 list-none overflow-hidden rounded-xl border border-line bg-surface p-0"
    >
      {decisions.map((decision) => {
        const affected = decision.affected_item_ids.map((id) => titles.get(id) ?? id);
        const show = () => {
          onShowEvidence({ type: 'decision', id: decision.id });
        };
        return (
          <li
            key={decision.id}
            aria-label={decision.subject}
            className="flex flex-col gap-1.5 border-t border-line px-3.5 py-3 text-sm first:border-t-0"
          >
            <div className="flex flex-wrap items-center gap-2">
              <Tag tone={tone(decision)}>{decisionLabel(decision)}</Tag>
              <strong className="font-semibold">{decision.subject}</strong>
              <span className="ml-auto flex flex-wrap gap-1">
                {decision.evidence.map((reference) => (
                  <SourceCitationChip
                    key={`${reference.block_id}-${reference.quote ?? ''}`}
                    projectId={projectId}
                    sourceVersionId={reference.source_version_id}
                    blockId={reference.block_id}
                    about={decision.subject}
                    onOpen={show}
                  />
                ))}
              </span>
            </div>
            <p>{decision.question}</p>
            {decision.status === 'answered' && (
              <>
                <blockquote className="m-0 rounded-lg border border-line bg-surface-2 px-3 py-2 whitespace-pre-wrap">
                  {decision.answer}
                </blockquote>
                <span className="text-xs text-subtle">
                  Answered by {reviewerName(decision.decided_by)}
                </span>
              </>
            )}
            {decision.status === 'skipped' && (
              <span className="text-xs text-subtle">
                Skipped by {reviewerName(decision.decided_by)}. No answer was assumed.
              </span>
            )}
            <span className="text-xs text-subtle">
              {decision.status === 'answered' ? 'Confirms' : 'Blocks'}:{' '}
              {affected.length > 0 ? affected.join('; ') : 'no story yet'}
            </span>
            {decision.status !== 'answered' && draft?.canAnswer && (
              <DecisionAnswer
                decision={decision}
                saving={isSaving(draft, `decision:${decision.id}`)}
                disabled={isLocked(draft)}
                error={errorFor(draft, `decision:${decision.id}`)}
                onAnswer={(answer, onSaved) => {
                  draft.commands.send({ type: 'answer', decisionId: decision.id, answer }, onSaved);
                }}
              />
            )}
          </li>
        );
      })}
    </ul>
  );
}

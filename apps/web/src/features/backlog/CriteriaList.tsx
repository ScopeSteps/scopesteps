import { CriterionRow } from './CriterionRow';
import { isLocked } from './draftControls';
import type { DraftControls } from './draftControls';
import { reviewSuggestion } from './types';
import type { BacklogItem, ClaimRef } from './types';

interface CriteriaListProps {
  projectId: string;
  item: BacklogItem;
  onShowEvidence: (claim: ClaimRef) => void;
  /** The draft's controls, or null when the version or the reader's role is read-only. */
  draft: DraftControls | null;
  /** Called before the reviewer's action is sent, for example to keep a row open. */
  onReviewed?: () => void;
}

/** An epic's or story's acceptance criteria, where an editor accepts or rejects suggestions. */
export function CriteriaList({
  projectId,
  item,
  onShowEvidence,
  draft,
  onReviewed,
}: CriteriaListProps) {
  const locked = draft ? isLocked(draft) : true;
  return (
    <ul
      aria-label={`Acceptance criteria for ${item.title}`}
      className="m-0 flex list-none flex-col gap-2.5 p-0"
    >
      {item.criteria.map((criterion) => (
        <CriterionRow
          key={criterion.id}
          projectId={projectId}
          criterion={criterion}
          onShowEvidence={onShowEvidence}
          busy={locked}
          canUndo={draft?.canEdit === true}
          onReviewSuggestion={
            draft?.canEdit
              ? (status) => {
                  onReviewed?.();
                  draft.commands.send({
                    type: 'edit',
                    itemId: item.id,
                    patch: reviewSuggestion(item, criterion.id, status),
                  });
                }
              : draft?.canReviewSuggestions
                ? (status) => {
                    if (status === 'pending') {
                      return;
                    }
                    onReviewed?.();
                    draft.commands.send({
                      type: 'suggestion',
                      itemId: item.id,
                      criterionId: criterion.id,
                      outcome: status,
                    });
                  }
                : undefined
          }
        />
      ))}
    </ul>
  );
}

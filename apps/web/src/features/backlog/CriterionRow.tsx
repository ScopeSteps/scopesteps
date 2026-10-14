import { Button } from '@/components/Button';
import { CitationChip } from '@/components/CitationChip';
import { Tag } from '@/components/Tag';
import { SourceCitationChip } from '@/features/sources';
import { cx } from '@/lib/cx';

import { criterionTags, suggestionStatus } from './types';
import type { ClaimRef, Criterion, SuggestionStatus } from './types';

interface CriterionRowProps {
  projectId: string;
  criterion: Criterion;
  onShowEvidence: (claim: ClaimRef) => void;
  /** Accepts, rejects or reopens a suggestion; absent when the reader cannot edit. */
  onReviewSuggestion?: ((status: SuggestionStatus) => void) | undefined;
  busy?: boolean;
}

export function CriterionRow({
  projectId,
  criterion,
  onShowEvidence,
  onReviewSuggestion,
  busy = false,
}: CriterionRowProps) {
  const suggestion = suggestionStatus(criterion);
  const show = () => {
    onShowEvidence({ type: 'criterion', id: criterion.id });
  };
  const hasEvidence = criterion.evidence.length + criterion.confirmed_by.length > 0;

  return (
    <li
      className={cx(
        'flex flex-col gap-1.5 rounded-lg border px-3 py-[9px] text-sm',
        suggestion === 'pending'
          ? 'border-dashed border-warn-line bg-warn-soft'
          : 'border-line bg-surface-2',
        suggestion === 'rejected' && 'opacity-60',
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        {criterionTags(criterion).map((tag) => (
          <Tag key={tag.label} tone={tag.tone}>
            {tag.label}
          </Tag>
        ))}
        {suggestion === 'rejected' ? (
          onReviewSuggestion && (
            <Button
              size="sm"
              variant="ghost"
              className="ml-auto"
              disabled={busy}
              aria-label={`Undo rejecting: ${criterion.text}`}
              onClick={() => {
                onReviewSuggestion('pending');
              }}
            >
              Undo
            </Button>
          )
        ) : (
          <span className="ml-auto flex flex-wrap gap-1">
            {criterion.evidence.map((reference) => (
              <SourceCitationChip
                key={`${reference.block_id}-${reference.quote ?? ''}`}
                projectId={projectId}
                sourceVersionId={reference.source_version_id}
                blockId={reference.block_id}
                about={criterion.text}
                onOpen={show}
              />
            ))}
            {criterion.confirmed_by.map((decisionId) => (
              <CitationChip
                key={decisionId}
                aria-label={`Answer, evidence for: ${criterion.text}`}
                onClick={show}
              >
                Answer
              </CitationChip>
            ))}
            {!hasEvidence && <span className="text-xs text-subtle">No evidence</span>}
          </span>
        )}
      </div>
      {suggestion === 'rejected' ? (
        <p className="text-muted line-through">{criterion.text}</p>
      ) : (
        <p>{criterion.text}</p>
      )}
      {suggestion === 'pending' && onReviewSuggestion && (
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="primary"
            disabled={busy}
            aria-label={`Accept suggestion: ${criterion.text}`}
            onClick={() => {
              onReviewSuggestion('accepted');
            }}
          >
            Accept
          </Button>
          <Button
            size="sm"
            disabled={busy}
            aria-label={`Reject suggestion: ${criterion.text}`}
            onClick={() => {
              onReviewSuggestion('rejected');
            }}
          >
            Reject
          </Button>
        </div>
      )}
    </li>
  );
}

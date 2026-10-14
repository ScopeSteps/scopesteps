import { CitationChip } from '@/components/CitationChip';
import { Tag } from '@/components/Tag';
import { SourceCitationChip } from '@/features/sources';
import { cx } from '@/lib/cx';

import { ORIGINS } from './types';
import type { ClaimRef, Criterion } from './types';

interface CriterionRowProps {
  projectId: string;
  criterion: Criterion;
  onShowEvidence: (claim: ClaimRef) => void;
}

export function CriterionRow({ projectId, criterion, onShowEvidence }: CriterionRowProps) {
  const origin = ORIGINS[criterion.origin];
  const show = () => {
    onShowEvidence({ type: 'criterion', id: criterion.id });
  };
  const hasEvidence = criterion.evidence.length + criterion.confirmed_by.length > 0;

  return (
    <li
      className={cx(
        'flex flex-col gap-1.5 rounded-lg border px-3 py-[9px] text-sm',
        criterion.origin === 'proposed'
          ? 'border-dashed border-warn-line bg-warn-soft'
          : 'border-line bg-surface-2',
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Tag tone={origin.tone}>{origin.label}</Tag>
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
      </div>
      <p>{criterion.text}</p>
    </li>
  );
}

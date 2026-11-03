import type { ReactNode } from 'react';

import { DiffTag } from '@/components/DiffTag';
import { Tag } from '@/components/Tag';
import { SourceCitationChip } from '@/features/sources';

import type { ExclusionOutcome } from './candidate';
import type { ClaimRef, EvidenceRef, ScopeNote } from './types';

/** Work the baseline ruled out, which a proposed change brings back if a Product owner
 * says yes. */
export interface RemovedExclusionRow {
  summary: string;
  evidence: EvidenceRef[];
  outcome: ExclusionOutcome;
  /** Opens the scope decision that settles it. */
  onOpen: () => void;
}

interface ScopeRowsProps {
  projectId: string;
  notes: ScopeNote[];
  removed?: RemovedExclusionRow[];
  onShowEvidence: (claim: ClaimRef) => void;
}

const REMOVED_TAG: Record<ExclusionOutcome, ReactNode> = {
  pending: <DiffTag kind="removed" label="May come back" />,
  reversed: <DiffTag kind="removed" label="Back in scope" />,
  kept: <Tag>Kept out</Tag>,
};

const REMOVED_NOTE: Record<ExclusionOutcome, string> = {
  pending: 'Ruled out in the baseline. It comes back into scope only if a Product owner says yes.',
  reversed: 'Ruled out in the baseline. A Product owner brought it back into scope.',
  kept: 'Ruled out in the baseline. A Product owner kept it out of scope.',
};

function Row({
  projectId,
  summary,
  evidence,
  note,
  tag,
  onOpen,
}: {
  projectId: string;
  summary: string;
  evidence: EvidenceRef[];
  note: string;
  tag?: ReactNode;
  onOpen: () => void;
}) {
  return (
    <li className="flex flex-col gap-1 border-t border-line px-3.5 py-3 text-sm first:border-t-0">
      <div className="flex flex-wrap items-center gap-2.5">
        {tag}
        <span className="min-w-0 flex-1 font-semibold text-muted line-through">{summary}</span>
        <span className="flex flex-wrap gap-1">
          {evidence.map((reference) => (
            <SourceCitationChip
              key={`${reference.block_id}-${reference.quote ?? ''}`}
              projectId={projectId}
              sourceVersionId={reference.source_version_id}
              blockId={reference.block_id}
              about={summary}
              onOpen={onOpen}
            />
          ))}
        </span>
      </div>
      <span className="text-xs text-subtle">{note}</span>
    </li>
  );
}

/** Work the sources keep out, or that was suggested and not committed. */
export function ScopeRows({ projectId, notes, removed = [], onShowEvidence }: ScopeRowsProps) {
  return (
    <ul
      aria-label="Out of scope"
      className="m-0 list-none overflow-hidden rounded-xl border border-line bg-surface p-0"
    >
      {notes.map((note, index) => (
        <Row
          key={note.summary}
          projectId={projectId}
          summary={note.summary}
          evidence={note.evidence}
          note={note.kind === 'excluded' ? 'Ruled out in the sources' : 'Suggested, not agreed'}
          onOpen={() => {
            onShowEvidence({ type: 'scope', index });
          }}
        />
      ))}
      {removed.map((row) => (
        <Row
          key={`removed-${row.summary}`}
          projectId={projectId}
          summary={row.summary}
          evidence={row.evidence}
          note={REMOVED_NOTE[row.outcome]}
          tag={REMOVED_TAG[row.outcome]}
          onOpen={row.onOpen}
        />
      ))}
    </ul>
  );
}

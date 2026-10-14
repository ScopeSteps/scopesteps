import { SourceCitationChip } from '@/features/sources';

import type { ClaimRef, ScopeNote } from './types';

interface ScopeRowsProps {
  projectId: string;
  notes: ScopeNote[];
  onShowEvidence: (claim: ClaimRef) => void;
}

/** Work the sources keep out, or that was suggested and not committed. */
export function ScopeRows({ projectId, notes, onShowEvidence }: ScopeRowsProps) {
  return (
    <ul
      aria-label="Out of scope"
      className="m-0 list-none overflow-hidden rounded-xl border border-line bg-surface p-0"
    >
      {notes.map((note, index) => (
        <li
          key={note.summary}
          className="flex flex-col gap-1 border-t border-line px-3.5 py-3 text-sm first:border-t-0"
        >
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="min-w-0 flex-1 font-semibold text-muted line-through">
              {note.summary}
            </span>
            <span className="flex flex-wrap gap-1">
              {note.evidence.map((reference) => (
                <SourceCitationChip
                  key={`${reference.block_id}-${reference.quote ?? ''}`}
                  projectId={projectId}
                  sourceVersionId={reference.source_version_id}
                  blockId={reference.block_id}
                  about={note.summary}
                  onOpen={() => {
                    onShowEvidence({ type: 'scope', index });
                  }}
                />
              ))}
            </span>
          </div>
          <span className="text-xs text-subtle">
            {note.kind === 'excluded' ? 'Excluded by the sources' : 'Suggested, not committed'}
          </span>
        </li>
      ))}
    </ul>
  );
}

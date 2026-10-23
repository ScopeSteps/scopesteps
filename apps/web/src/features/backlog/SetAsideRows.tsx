import { SourceCitationChip } from '@/features/sources';

import type { ClaimRef, SetAsideNote } from './types';

interface SetAsideRowsProps {
  projectId: string;
  notes: SetAsideNote[];
  onShowEvidence: (claim: ClaimRef) => void;
}

/**
 * The paragraphs the agent read as background and used nowhere in the backlog, in its own words,
 * so a reviewer can check that none of them states a requirement. Nothing here is scope.
 */
export function SetAsideRows({ projectId, notes, onShowEvidence }: SetAsideRowsProps) {
  return (
    <ul
      aria-label="Set aside as context"
      className="m-0 list-none overflow-hidden rounded-xl border border-line bg-surface p-0"
    >
      {notes.map((note, index) => (
        <li
          key={`${String(index)}-${note.summary}`}
          className="flex flex-wrap items-center gap-2.5 border-t border-line px-3.5 py-3 text-sm first:border-t-0"
        >
          <span className="min-w-0 flex-1 text-muted">{note.summary}</span>
          <span className="flex flex-wrap gap-1">
            {note.evidence.map((reference) => (
              <SourceCitationChip
                key={`${reference.block_id}-${reference.quote ?? ''}`}
                projectId={projectId}
                sourceVersionId={reference.source_version_id}
                blockId={reference.block_id}
                about={note.summary}
                onOpen={() => {
                  onShowEvidence({ type: 'context', index });
                }}
              />
            ))}
          </span>
        </li>
      ))}
    </ul>
  );
}

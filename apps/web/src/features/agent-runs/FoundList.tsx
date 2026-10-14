import { CitationChip } from '@/components/CitationChip';
import { Tag } from '@/components/Tag';
import type { TagTone } from '@/components/Tag';
import { cx } from '@/lib/cx';

import type { Statement } from './types';

const KINDS: Record<Statement['kind'], { label: string; tone: TagTone }> = {
  confirmed: { label: 'Decision', tone: 'accent' },
  exclusion: { label: 'Excluded', tone: 'neutral' },
  proposal: { label: 'Proposal', tone: 'warn' },
  conflict: { label: 'Conflict', tone: 'bad' },
  open_question: { label: 'Unknown', tone: 'bad' },
  context: { label: 'Context', tone: 'neutral' },
};

interface FoundListProps {
  statements: Statement[];
  onShowCitation: (statementId: string, citation: number) => void;
}

/** What the agent found in the sources, by kind, each with the blocks it cites. */
export function FoundList({ statements, onShowCitation }: FoundListProps) {
  return (
    <>
      <p>I read the sources and sorted what they say.</p>
      <ul
        aria-label="What the agent found"
        className="m-0 flex list-none flex-col gap-1.5 p-0 text-sm"
      >
        {statements.map((statement) => (
          <li
            key={statement.id}
            className="grid grid-cols-[78px_minmax(0,1fr)] items-center gap-x-2.5 gap-y-1 sm:grid-cols-[78px_minmax(0,1fr)_auto]"
          >
            <Tag tone={KINDS[statement.kind].tone} className="justify-self-start">
              {KINDS[statement.kind].label}
            </Tag>
            <span className={cx(statement.kind === 'exclusion' && 'text-muted line-through')}>
              {statement.summary}
            </span>
            <span className="col-start-2 flex flex-wrap gap-1 sm:col-start-auto">
              {statement.citations.map((citation, index) => (
                <CitationChip
                  key={`${citation.block_id}-${String(index)}`}
                  onClick={() => {
                    onShowCitation(statement.id, index);
                  }}
                >
                  {citation.block_id}
                </CitationChip>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}

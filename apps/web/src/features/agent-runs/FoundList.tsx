import { Tag } from '@/components/Tag';
import type { TagTone } from '@/components/Tag';
import { cx } from '@/lib/cx';

import { RunCitationChip } from './RunCitationChip';
import type { Run, Statement } from './types';

const KINDS: Record<Statement['kind'], { label: string; tone: TagTone }> = {
  confirmed: { label: 'Decision', tone: 'accent' },
  exclusion: { label: 'Excluded', tone: 'neutral' },
  proposal: { label: 'Proposal', tone: 'warn' },
  conflict: { label: 'Conflict', tone: 'bad' },
  open_question: { label: 'Unknown', tone: 'bad' },
  context: { label: 'Context', tone: 'neutral' },
};

interface FoundListProps {
  projectId: string;
  run: Run;
  statements: Statement[];
  onShowCitation: (statementId: string, citation: number) => void;
}

/** What the agent found in the sources, by kind, each with the blocks it cites. */
export function FoundList({ projectId, run, statements, onShowCitation }: FoundListProps) {
  return (
    <>
      <p>I read the sources and sorted what they say.</p>
      <ul
        aria-label="What the agent found"
        className="m-0 flex list-none flex-col gap-1.5 p-0 text-sm"
      >
        {statements.map((statement) => (
          // From sm up the citations sit beside the summary, as wide as their chips but never
          // more than 40% of the row, so many citations wrap instead of squeezing the summary.
          <li
            key={statement.id}
            className="grid grid-cols-[78px_minmax(0,1fr)] items-center gap-x-2.5 gap-y-1 sm:grid-cols-[78px_minmax(0,1fr)_fit-content(40%)]"
          >
            <Tag tone={KINDS[statement.kind].tone} className="justify-self-start">
              {KINDS[statement.kind].label}
            </Tag>
            <span className={cx(statement.kind === 'exclusion' && 'text-muted line-through')}>
              {statement.summary}
            </span>
            <span className="col-start-2 flex flex-wrap gap-1 sm:col-start-auto">
              {statement.citations.map((citation, index) => (
                <RunCitationChip
                  key={`${citation.block_id}-${String(index)}`}
                  projectId={projectId}
                  run={run}
                  label={citation.block_id}
                  about={statement.summary}
                  onOpen={() => {
                    onShowCitation(statement.id, index);
                  }}
                />
              ))}
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}

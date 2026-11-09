import { useId, useState } from 'react';

import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { cx } from '@/lib/cx';

import { RunEvidenceSheet } from './RunEvidenceSheet';
import type { Run } from './types';

type Coverage = NonNullable<Run['coverage']>;

interface CoveragePanelProps {
  projectId: string;
  /** The run that wrote the draft. */
  run: Run;
  coverage: Coverage;
}

interface OpenQuote {
  statementId: string;
  citation: number;
}

function requirements(count: number): string {
  return `${String(count)} confirmed ${count === 1 ? 'requirement' : 'requirements'}`;
}

/**
 * How many confirmed requirements the agent's draft covers with a story, and the ones it does
 * not, each with the quote that states it (ADR 0028). Counted when the agent wrote the draft.
 */
export function CoveragePanel({ projectId, run, coverage }: CoveragePanelProps) {
  const listId = useId();
  const missing = coverage.uncovered.length;
  const [open, setOpen] = useState(missing > 0);
  const [quote, setQuote] = useState<OpenQuote | null>(null);
  const complete = missing === 0;

  return (
    <section
      aria-labelledby={`${listId}-heading`}
      className={cx(
        'flex flex-col gap-2 rounded-xl border px-3.5 py-3',
        complete ? 'border-line bg-surface' : 'border-warn-line bg-warn-soft',
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 id={`${listId}-heading`} className="flex-1 text-sm font-semibold">
          Requirements covered:{' '}
          <span className="font-mono tabular-nums">
            {String(coverage.covered)} of {String(coverage.confirmed)}
          </span>
        </h3>
        {!complete && (
          <Button
            size="sm"
            variant="ghost"
            aria-expanded={open}
            aria-controls={listId}
            onClick={() => {
              setOpen((current) => !current);
            }}
          >
            <span aria-hidden="true" className={cx('transition-transform', open && 'rotate-90')}>
              <Icon name="right" size={14} />
            </span>
            {open ? 'Hide' : 'Show'} the {missing === 1 ? 'one' : String(missing)} not covered
          </Button>
        )}
      </div>
      <p className="text-xs text-muted">
        {coverage.confirmed === 0
          ? 'The sources confirm no requirements yet.'
          : complete
            ? `Every one of the ${requirements(coverage.confirmed)} has a story.`
            : `${requirements(missing)} in the sources ${missing === 1 ? 'has' : 'have'} no story yet. Add a story, or check that ${missing === 1 ? 'it is' : 'they are'} not needed.`}{' '}
        Counted when the agent wrote this draft.
      </p>
      {!complete && open && (
        <ul
          id={listId}
          aria-label="Not covered by a story"
          className="m-0 flex list-none flex-col gap-2 p-0"
        >
          {coverage.uncovered.map((statement) => (
            <li
              key={statement.statement_id}
              className="flex flex-col gap-1.5 rounded-lg border border-line bg-surface px-3 py-2"
            >
              <p className="text-sm">{statement.summary}</p>
              <div className="flex flex-wrap gap-1.5">
                {statement.citations.map((citation, index) => (
                  <Button
                    // Citations keep their order, so the position is a stable key.
                    key={index}
                    size="sm"
                    variant="ghost"
                    aria-label={`Show the quote for “${statement.summary}”${statement.citations.length > 1 ? ` (${String(index + 1)} of ${String(statement.citations.length)})` : ''}`}
                    onClick={() => {
                      setQuote({ statementId: statement.statement_id, citation: index });
                    }}
                  >
                    <span className="max-w-[40ch] truncate">“{citation.quote}”</span>
                  </Button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
      {quote && (
        <RunEvidenceSheet
          projectId={projectId}
          run={run}
          evidence={{
            type: 'statement',
            runId: run.id,
            id: quote.statementId,
            citation: quote.citation,
          }}
          onClose={() => {
            setQuote(null);
          }}
        />
      )}
    </section>
  );
}

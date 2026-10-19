import { Fragment, useId, useState } from 'react';

import { Button } from '@/components/Button';
import { Tag } from '@/components/Tag';

import type { JiraRow } from './exportFile';

const COLUMNS = ['ID', 'Type', 'Summary', 'Parent'];
const HEAD =
  'border-b border-line bg-surface-2 px-3 py-2 text-left text-xs font-semibold text-subtle';
const CELL = 'px-3 py-2.5 align-top';

/** The rows of the CSV file as a table, each description behind a toggle on its row. */
export function CsvPreview({ rows }: { rows: readonly JiraRow[] }) {
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const idPrefix = useId();

  if (rows.length === 0) {
    return (
      <p className="rounded-lg border border-line bg-surface-2 p-3 text-subtle">
        This version has no epics or stories, so the file holds only its header row.
      </p>
    );
  }

  function toggle(issueId: string) {
    setOpen((current) => {
      const next = new Set(current);
      if (!next.delete(issueId)) {
        next.add(issueId);
      }
      return next;
    });
  }

  return (
    <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-line bg-surface">
      <table className="w-full border-collapse text-[13px]">
        <caption className="sr-only">Rows of the CSV file</caption>
        <thead className="sticky top-0">
          <tr>
            {COLUMNS.map((column) => (
              <th key={column} scope="col" className={HEAD}>
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const expanded = open.has(row.issueId);
            const descriptionId = `${idPrefix}-${row.issueId}`;
            return (
              <Fragment key={row.issueId}>
                <tr className="border-b border-line last:border-b-0">
                  <td className={`${CELL} font-mono text-subtle tabular-nums`}>{row.issueId}</td>
                  <td className={CELL}>
                    <Tag tone={row.issueType === 'Epic' ? 'accent' : 'neutral'}>
                      {row.issueType}
                    </Tag>
                  </td>
                  <th scope="row" className={`${CELL} text-left font-normal`}>
                    <span className="[overflow-wrap:anywhere]">{row.summary}</span>
                    {row.description && (
                      <div className="mt-1 -ml-2.5">
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-expanded={expanded}
                          aria-controls={expanded ? descriptionId : undefined}
                          onClick={() => {
                            toggle(row.issueId);
                          }}
                        >
                          {expanded ? 'Hide description' : 'Show description'}
                        </Button>
                      </div>
                    )}
                  </th>
                  <td className={`${CELL} font-mono text-subtle tabular-nums`}>{row.parent}</td>
                </tr>
                {expanded && (
                  <tr className="border-b border-line last:border-b-0">
                    <td colSpan={COLUMNS.length} className="bg-surface-2 px-3 py-2.5">
                      <p
                        id={descriptionId}
                        className="text-xs [overflow-wrap:anywhere] whitespace-pre-wrap text-muted"
                      >
                        {row.description}
                      </p>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

import type { ReactNode } from 'react';

import { DiffTag } from '@/components/DiffTag';
import type { DiffKind } from '@/components/DiffTag';
import { Tag } from '@/components/Tag';
import { cx } from '@/lib/cx';

import type { BacklogItem } from './types';

interface EpicCardProps {
  epic: BacklogItem;
  /** The stories the card lists now, which a filter can make fewer than `total`. */
  listed: number;
  total: number;
  /** On a change candidate: what the change does to the epic (null when unchanged). */
  diff?: DiffKind | null | undefined;
  /** The epic's story rows. */
  children: ReactNode;
}

function storyCount(listed: number, total: number): string {
  const noun = total === 1 ? 'story' : 'stories';
  return listed === total
    ? `${String(total)} ${noun}`
    : `${String(listed)} of ${String(total)} ${noun}`;
}

/** An epic as a card: its header names it as an epic, and its stories sit inside the card. */
export function EpicCard({ epic, listed, total, diff, children }: EpicCardProps) {
  const headingId = `epic-${epic.id}`;
  return (
    <section
      aria-labelledby={headingId}
      className="overflow-hidden rounded-xl border border-line bg-surface"
    >
      <div className="flex flex-col gap-1 px-3.5 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <h4
            id={headingId}
            className="flex min-w-0 flex-1 flex-wrap items-center gap-2 text-[15px] font-semibold"
          >
            <Tag tone="accent">Epic</Tag>{' '}
            <span className={cx('min-w-0', diff === 'removed' && 'text-muted line-through')}>
              {epic.title}
            </span>{' '}
            {diff && <DiffTag kind={diff} />}
          </h4>
          <span className="font-mono text-xs text-subtle tabular-nums">
            {storyCount(listed, total)}
          </span>
        </div>
        {epic.description && <p className="text-[13px] text-muted">{epic.description}</p>}
      </div>
      {total === 0 ? (
        <p className="border-t border-line px-3.5 py-3 text-xs text-subtle">
          No stories in this epic yet.
        </p>
      ) : (
        listed > 0 && (
          <ul
            aria-label={`Stories in ${epic.title}`}
            className="m-0 list-none border-t border-line p-0"
          >
            {children}
          </ul>
        )
      )}
    </section>
  );
}

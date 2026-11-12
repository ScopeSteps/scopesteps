import { useId } from 'react';
import type { ReactNode } from 'react';

import { DiffTag } from '@/components/DiffTag';
import type { DiffKind } from '@/components/DiffTag';
import { Icon } from '@/components/Icon';
import { Tag } from '@/components/Tag';
import { JiraKeyLink } from '@/features/jira';
import type { JiraIssueLink } from '@/features/jira';
import { cx } from '@/lib/cx';

import { CriteriaList } from './CriteriaList';
import { DiscussionButton } from './DiscussionButton';
import type { DraftControls } from './draftControls';
import { attention } from './types';
import type { BacklogItem, ClaimRef, ItemDiscussions } from './types';

interface EpicCardProps {
  projectId: string;
  epic: BacklogItem;
  onShowEvidence: (claim: ClaimRef) => void;
  /** The draft's controls, or null when the version or the reader's role is read-only. */
  draft: DraftControls | null;
  /** The stories the card lists now, which a filter can make fewer than `total`. */
  listed: number;
  total: number;
  /** On a change candidate: what the change does to the epic (null when unchanged). */
  diff?: DiffKind | null | undefined;
  discussions?: ItemDiscussions | undefined;
  /** The epic's Jira issue, once published. */
  jira?: JiraIssueLink | undefined;
  /** Whether the description, criteria and stories show; the header always does. */
  expanded?: boolean;
  /** Opens or closes the card. Without it the card cannot be closed. */
  onToggle?: (() => void) | undefined;
  /** The epic's story rows. */
  children: ReactNode;
}

function storyCount(listed: number, total: number): string {
  const noun = total === 1 ? 'story' : 'stories';
  return listed === total
    ? `${String(total)} ${noun}`
    : `${String(listed)} of ${String(total)} ${noun}`;
}

/**
 * An epic as a card: its header names it as an epic, its acceptance criteria follow the
 * description, and its stories sit inside the card.
 */
export function EpicCard({
  projectId,
  epic,
  onShowEvidence,
  draft,
  listed,
  total,
  diff,
  discussions,
  jira,
  expanded = true,
  onToggle,
  children,
}: EpicCardProps) {
  const headingId = `epic-${epic.id}`;
  const bodyId = useId();
  const { suggestions } = attention(epic.blockers);
  const title = (
    <>
      <Tag tone="accent">Epic</Tag>{' '}
      <span className={cx('min-w-0', diff === 'removed' && 'text-muted line-through')}>
        {epic.title}
      </span>{' '}
      {diff && <DiffTag kind={diff} />}
      {suggestions > 0 && (
        <Tag tone="warn">
          {suggestions} {suggestions === 1 ? 'suggestion' : 'suggestions'}
        </Tag>
      )}
    </>
  );
  return (
    <section
      aria-labelledby={headingId}
      className="overflow-hidden rounded-xl border border-line bg-surface"
    >
      <div className="flex flex-col gap-1 px-3.5 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <h4 id={headingId} className="min-w-0 flex-1 text-[15px] font-semibold">
            {onToggle ? (
              <button
                type="button"
                aria-expanded={expanded}
                aria-controls={bodyId}
                onClick={onToggle}
                className="-mx-1.5 flex w-[calc(100%+0.75rem)] cursor-pointer flex-wrap items-center gap-2 rounded-md px-1.5 py-1 text-left hover:bg-hover"
              >
                <span
                  aria-hidden="true"
                  className={cx('text-subtle transition-transform', expanded && 'rotate-90')}
                >
                  <Icon name="right" size={16} />
                </span>
                {title}
              </button>
            ) : (
              <span className="flex flex-wrap items-center gap-2">{title}</span>
            )}
          </h4>
          <span className="font-mono text-xs text-subtle tabular-nums">
            {storyCount(listed, total)}
          </span>
          {jira && <JiraKeyLink link={jira} />}
          {discussions && <DiscussionButton item={epic} discussions={discussions} />}
        </div>
        {expanded && epic.description && (
          <p className="text-[13px] whitespace-pre-line text-muted">{epic.description}</p>
        )}
        {expanded && epic.criteria.length > 0 && (
          <div className="mt-1.5 flex flex-col gap-1.5">
            <p className="text-xs font-semibold text-subtle">Acceptance criteria</p>
            <CriteriaList
              projectId={projectId}
              item={epic}
              onShowEvidence={onShowEvidence}
              draft={draft}
            />
          </div>
        )}
      </div>
      <div id={bodyId} hidden={!expanded}>
        {expanded &&
          (total === 0 ? (
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
          ))}
      </div>
    </section>
  );
}

import { Icon } from '@/components/Icon';

import type { BacklogItem, ItemDiscussions } from './types';

interface DiscussionButtonProps {
  item: BacklogItem;
  discussions: ItemDiscussions;
}

/** A speech bubble with the item's open discussions, which opens them beside the backlog. */
export function DiscussionButton({ item, discussions }: DiscussionButtonProps) {
  const open = discussions.counts[item.id] ?? 0;
  return (
    <button
      type="button"
      aria-label={
        open === 0
          ? `Discuss ${item.title}`
          : `Discussion on ${item.title}, ${String(open)} open ${open === 1 ? 'thread' : 'threads'}`
      }
      onClick={() => {
        discussions.onOpen({ id: item.id, title: item.title });
      }}
      className="inline-flex min-h-[30px] min-w-[30px] shrink-0 cursor-pointer items-center justify-center gap-1 rounded-md px-1.5 text-subtle hover:bg-hover hover:text-fg"
    >
      <Icon name="discussion" size={16} />
      {open > 0 && <span className="font-mono text-xs font-semibold tabular-nums">{open}</span>}
    </button>
  );
}

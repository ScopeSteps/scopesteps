import { useId, useState } from 'react';

import { Avatar } from '@/components/Avatar';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { Tag } from '@/components/Tag';
import { cx } from '@/lib/cx';

import { participation } from './types';
import type { Participant } from './types';

/** Initials shown before the rest are counted as "+N". */
const SHOWN_INITIALS = 5;

interface ThreadPeopleProps {
  participants: readonly Participant[];
  userId: string | null;
  following: boolean;
  /** Follows or stops following the thread; absent while it cannot change. */
  onFollow: (following: boolean) => void;
  followBusy: boolean;
}

/**
 * Who is in a discussion: everyone who wrote, was mentioned or follows, as initials at the top,
 * and a list that opens with what each did. Your own follow switch sits with it.
 */
export function ThreadPeople({
  participants,
  userId,
  following,
  onFollow,
  followBusy,
}: ThreadPeopleProps) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const extra = participants.length - SHOWN_INITIALS;
  const count = participants.length;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {count > 0 && (
          <button
            type="button"
            aria-expanded={open}
            aria-controls={listId}
            onClick={() => {
              setOpen((current) => !current);
            }}
            className="-ml-1 flex cursor-pointer items-center gap-2 rounded-md px-1 py-0.5 text-xs text-muted hover:bg-hover"
          >
            <span className="flex -space-x-1.5">
              {participants.slice(0, SHOWN_INITIALS).map((person) => (
                <span
                  key={person.user_id}
                  className={cx(
                    'rounded-full ring-2 ring-surface',
                    person.left_project && 'opacity-50',
                  )}
                >
                  <Avatar name={person.display_name} size={24} />
                </span>
              ))}
            </span>
            {extra > 0 && <span className="font-mono tabular-nums">+{extra}</span>}
            <span>
              People in this discussion <span className="font-mono tabular-nums">({count})</span>
            </span>
            <span
              aria-hidden="true"
              className={cx('text-subtle transition-transform', open && 'rotate-90')}
            >
              <Icon name="right" size={14} />
            </span>
          </button>
        )}
        <span className="ml-auto">
          <Button
            size="sm"
            variant="ghost"
            aria-pressed={following}
            title={following ? 'Stop following to get no reply notifications' : undefined}
            disabled={followBusy}
            onClick={() => {
              onFollow(!following);
            }}
          >
            {following ? 'Following' : 'Follow'}
          </Button>
        </span>
      </div>
      {open && (
        <ul
          id={listId}
          aria-label="People in this discussion"
          className="m-0 flex list-none flex-col gap-1.5 rounded-lg border border-line bg-surface-2 p-2.5"
        >
          {participants.map((person) => {
            const isMe = person.user_id === userId;
            return (
              <li key={person.user_id} className="flex flex-wrap items-center gap-2 text-[13px]">
                <span className={cx(person.left_project && 'opacity-50')}>
                  <Avatar name={person.display_name} size={24} />
                </span>
                <span className="flex min-w-0 flex-1 flex-col leading-tight">
                  <span className={cx('font-medium', person.left_project && 'text-muted')}>
                    {person.display_name}
                    {isMe && <span className="text-subtle"> (you)</span>}
                  </span>
                  <span className="text-xs text-subtle">{participation(person)}</span>
                </span>
                {person.left_project && <Tag>Left the project</Tag>}
                {isMe && (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={followBusy}
                    onClick={() => {
                      onFollow(!following);
                    }}
                  >
                    {following ? 'Stop following' : 'Follow this discussion'}
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

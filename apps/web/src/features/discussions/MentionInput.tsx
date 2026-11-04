import { useEffect, useId, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';

import { roleLabelOf } from '@/features/identity';
import { cx } from '@/lib/cx';

import { highlightParts, insertMention, queryAtCaret, removeMentionBefore } from './mentions';
import type { MentionText } from './mentions';
import type { MemberMatch } from './types';
import { useMemberSearch } from './useDiscussions';

interface MentionInputProps {
  projectId: string;
  label: string;
  value: MentionText;
  onChange: (next: MentionText) => void;
  placeholder?: string;
  rows?: number;
  disabled?: boolean;
  autoFocus?: boolean;
  /** Keys the picker has not taken, such as Cmd/Ctrl+Enter to post. */
  onKeyDown?: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
}

// One box's text and padding, so the highlights behind the text line up with it.
const FIELD_TEXT = 'border px-2.5 py-2 text-sm break-words whitespace-pre-wrap';

/**
 * A plain-text box where typing @ lists the project's members. A person picked shows as a
 * highlighted name, and Backspace after it removes all of it. The text stays plain: the
 * highlights are a layer behind a transparent textarea, so typing behaves as in any other box.
 */
export function MentionInput({
  projectId,
  label,
  value,
  onChange,
  placeholder,
  rows = 3,
  disabled = false,
  autoFocus = false,
  onKeyDown,
}: MentionInputProps) {
  const input = useRef<HTMLTextAreaElement>(null);
  const backdrop = useRef<HTMLDivElement>(null);
  const nextCaret = useRef<number | null>(null);
  const [caret, setCaret] = useState(0);
  const [dismissedAt, setDismissedAt] = useState<number | null>(null);
  const [active, setActive] = useState(0);
  const listId = useId();

  const typing = queryAtCaret(value, caret);
  const open = typing !== null && typing.start !== dismissedAt;
  const { data: found } = useMemberSearch(projectId, open ? typing.query : null);
  const members = found ?? [];
  const chosen = Math.min(active, Math.max(members.length - 1, 0));
  const showList = open && members.length > 0;

  // The caret can only move once React has put the new text in the box.
  useEffect(() => {
    if (nextCaret.current !== null && input.current) {
      input.current.setSelectionRange(nextCaret.current, nextCaret.current);
      setCaret(nextCaret.current);
      nextCaret.current = null;
    }
  }, [value.text]);

  function replace(next: { value: MentionText; caret: number }) {
    nextCaret.current = next.caret;
    onChange(next.value);
  }

  function pick(member: MemberMatch) {
    if (typing) {
      replace(
        insertMention(value, typing.start, caret, {
          userId: member.user_id,
          name: member.display_name,
        }),
      );
      setActive(0);
      input.current?.focus();
    }
  }

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (showList) {
      const step = event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0;
      if (step !== 0) {
        event.preventDefault();
        setActive((chosen + step + members.length) % members.length);
        return;
      }
      const member = members[chosen];
      if ((event.key === 'Enter' || event.key === 'Tab') && member) {
        event.preventDefault();
        pick(member);
        return;
      }
      if (event.key === 'Escape') {
        // Closes the list alone, not the sheet the box may be in.
        event.preventDefault();
        event.stopPropagation();
        setDismissedAt(typing.start);
        return;
      }
    }
    const { selectionStart, selectionEnd } = event.currentTarget;
    if (event.key === 'Backspace' && selectionStart === selectionEnd) {
      const removed = removeMentionBefore(value, selectionStart);
      if (removed) {
        event.preventDefault();
        replace(removed);
        return;
      }
    }
    onKeyDown?.(event);
  }

  return (
    <div className="relative">
      <div className="relative rounded-lg bg-surface">
        <div
          ref={backdrop}
          aria-hidden
          className={cx(
            FIELD_TEXT,
            'pointer-events-none absolute inset-0 overflow-hidden border-transparent text-transparent',
          )}
        >
          {highlightParts(value).map((part, index) =>
            part.mention ? (
              <mark key={index} className="rounded bg-accent-soft text-transparent">
                {part.text}
              </mark>
            ) : (
              <span key={index}>{part.text}</span>
            ),
          )}
        </div>
        <textarea
          ref={input}
          aria-label={label}
          aria-autocomplete="list"
          aria-controls={showList ? listId : undefined}
          aria-activedescendant={showList ? `${listId}-${String(chosen)}` : undefined}
          value={value.text}
          rows={rows}
          placeholder={placeholder}
          disabled={disabled}
          autoFocus={autoFocus}
          onChange={(event) => {
            setCaret(event.target.selectionStart);
            onChange({ ...value, text: event.target.value });
          }}
          onSelect={(event) => {
            setCaret(event.currentTarget.selectionStart);
          }}
          onScroll={(event) => {
            if (backdrop.current) {
              backdrop.current.scrollTop = event.currentTarget.scrollTop;
            }
          }}
          onKeyDown={keyDown}
          className={cx(
            FIELD_TEXT,
            'relative block w-full resize-y rounded-lg border-line bg-transparent text-fg focus:border-accent focus:shadow-focus focus:outline-none disabled:bg-surface-2',
          )}
        />
      </div>
      {showList && (
        <ul
          id={listId}
          role="listbox"
          aria-label="Project members"
          className="absolute inset-x-0 top-full z-[32] m-0 mt-1 flex max-h-56 list-none flex-col overflow-auto rounded-lg border border-line bg-surface p-1 shadow-pop"
        >
          {members.map((member, index) => (
            <li
              key={member.user_id}
              id={`${listId}-${String(index)}`}
              role="option"
              aria-selected={index === chosen}
              // Taken before the box loses focus, so the caret is still where the @ was typed.
              onMouseDown={(event) => {
                event.preventDefault();
                pick(member);
              }}
              className={cx(
                'flex cursor-pointer items-baseline justify-between gap-3 rounded-md px-2 py-1.5 text-sm',
                index === chosen && 'bg-hover',
              )}
            >
              <span className="min-w-0 truncate font-medium">{member.display_name}</span>
              <span className="flex-none text-xs text-subtle">{roleLabelOf(member.role)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

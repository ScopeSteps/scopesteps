import type { ReactNode } from 'react';

import { Tag } from '@/components/Tag';

import { Time } from './Time';
import type { Message } from './types';

/** A person's message, on the right, with who wrote it. Reviewer text is data: a text node. */
export function UserBubble({
  author,
  at,
  kind,
  text,
  footer,
}: {
  author: string;
  at: string | null;
  kind: Message['kind'];
  text: string;
  footer?: ReactNode;
}) {
  return (
    <div
      role="article"
      aria-label={`Message from ${author}`}
      className="flex flex-col items-end gap-1"
    >
      <span className="text-xs text-subtle">
        {author}
        {at && (
          <>
            {' · '}
            <Time at={at} />
          </>
        )}
      </span>
      {kind === 'change_request' && <Tag tone="accent">Change request</Tag>}
      <p className="m-0 max-w-[85%] rounded-2xl rounded-tr-md bg-surface-2 px-3.5 py-2.5 text-[15px] leading-[1.55] whitespace-pre-wrap">
        {text}
      </p>
      {footer}
    </div>
  );
}

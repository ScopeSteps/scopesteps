import { useId } from 'react';

import { Card } from '@/components/Card';
import { Tag } from '@/components/Tag';

import type { ThreadContext } from './threadContext';
import { Time } from './Time';
import type { Message } from './types';
import { useAuthorName } from './useAuthorName';

const DECISION: Partial<Record<Message['kind'], { label: string; tone: 'ok' | 'bad' | 'accent' }>> =
  {
    answer: { label: 'Answered', tone: 'ok' },
    skip: { label: 'Skipped', tone: 'bad' },
    answer_changed: { label: 'Answer changed', tone: 'accent' },
  };

/** An answer, skip or changed answer as it was recorded, with the question it settles. */
export function DecisionCard({ message, context }: { message: Message; context: ThreadContext }) {
  const authorName = useAuthorName(context.projectId);
  const headingId = useId();
  const decision = DECISION[message.kind];
  if (!decision) {
    return null;
  }
  const subject = message.question?.subject ?? 'A question';
  return (
    <div className="flex justify-end">
      <Card role="article" aria-labelledby={headingId} className="max-w-[85%]">
        <div className="flex flex-wrap items-center gap-2">
          <Tag tone={decision.tone}>{decision.label}</Tag>
          <span id={headingId} className="text-xs text-subtle">
            Decision · {subject}
          </span>
        </div>
        {message.kind === 'skip' ? (
          <p className="text-sm text-muted">No answer was given; the question stays open.</p>
        ) : (
          <p className="m-0 text-sm whitespace-pre-wrap">{message.text}</p>
        )}
        <span className="text-xs text-subtle">
          {authorName(message.author)} · <Time at={message.created_at} />
        </span>
      </Card>
    </div>
  );
}

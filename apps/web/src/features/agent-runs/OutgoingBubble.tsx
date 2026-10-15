import { Button } from '@/components/Button';

import type { OutgoingMessage } from './useOutbox';
import { UserBubble } from './UserBubble';

interface OutgoingBubbleProps {
  message: OutgoingMessage;
  author: string;
  onRetry: () => void;
  onDiscard: () => void;
}

/** A message not stored yet: sending, or failed with why and a way to retry it. */
export function OutgoingBubble({ message, author, onRetry, onDiscard }: OutgoingBubbleProps) {
  return (
    <UserBubble
      author={author}
      at={null}
      kind={message.kind}
      text={message.text}
      footer={
        message.status === 'sending' ? (
          <span role="status" className="text-xs text-subtle">
            Sending…
          </span>
        ) : (
          <div role="alert" className="flex flex-wrap items-center justify-end gap-2 text-[13px]">
            <span className="text-bad-ink">Not sent. {message.error}</span>
            <Button size="sm" onClick={onRetry}>
              Retry
            </Button>
            <Button size="sm" variant="ghost" onClick={onDiscard}>
              Discard
            </Button>
          </div>
        )
      }
    />
  );
}

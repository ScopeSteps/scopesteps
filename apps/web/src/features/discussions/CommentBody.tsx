import { Fragment } from 'react';

import { cx } from '@/lib/cx';

import { linkify } from './linkify';
import { bodyParts } from './mentions';
import type { Comment } from './types';

interface CommentBodyProps {
  comment: Comment;
  /** The person reading, whose own name stands out. */
  userId: string | null;
}

/**
 * A comment exactly as written: plain text, line breaks kept, web addresses as links and mentions
 * by the person's current name.
 */
export function CommentBody({ comment, userId }: CommentBodyProps) {
  return (
    <p className="text-sm break-words whitespace-pre-wrap">
      {bodyParts(comment.body ?? '').map((part, index) => {
        if (part.kind === 'mention') {
          const person = comment.mentions.find((m) => m.user_id === part.userId);
          return (
            <span
              key={index}
              className={cx(
                'rounded px-1 font-medium',
                part.userId === userId
                  ? 'bg-accent text-accent-fg'
                  : 'bg-accent-soft text-accent-ink',
              )}
            >
              @{person?.display_name ?? 'A former member'}
            </span>
          );
        }
        return (
          <Fragment key={index}>
            {linkify(part.text).map((piece, pieceIndex) =>
              piece.kind === 'link' ? (
                <a
                  key={pieceIndex}
                  href={piece.text}
                  target="_blank"
                  rel="noopener noreferrer nofollow"
                  className="text-accent-ink underline"
                >
                  {piece.text}
                </a>
              ) : (
                <Fragment key={pieceIndex}>{piece.text}</Fragment>
              ),
            )}
          </Fragment>
        );
      })}
    </p>
  );
}

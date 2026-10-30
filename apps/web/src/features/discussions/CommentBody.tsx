import { Fragment } from 'react';

import { linkify } from './linkify';

/** A comment exactly as written: plain text, line breaks kept, web addresses as links. */
export function CommentBody({ text }: { text: string }) {
  return (
    <p className="text-sm break-words whitespace-pre-wrap">
      {linkify(text).map((part, index) =>
        part.kind === 'link' ? (
          <a
            key={index}
            href={part.text}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="text-accent-ink underline"
          >
            {part.text}
          </a>
        ) : (
          <Fragment key={index}>{part.text}</Fragment>
        ),
      )}
    </p>
  );
}

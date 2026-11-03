import type { Comment } from './types';

/** A person named in a comment being written, by the text that stands for them. */
export interface PickedMention {
  userId: string;
  name: string;
}

/** A comment box's contents: what the person sees, and who the `@Name`s in it stand for. */
export interface MentionText {
  text: string;
  picked: PickedMention[];
}

export const EMPTY_MENTION_TEXT: MentionText = { text: '', picked: [] };

export type BodyPart = { kind: 'text'; text: string } | { kind: 'mention'; userId: string };

const TOKEN = /<@([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})>/gi;
const LONGEST_QUERY = 40;

function shownAs(name: string): string {
  return `@${name}`;
}

function longestFirst(picked: PickedMention[]): PickedMention[] {
  return [...picked].sort((a, b) => b.name.length - a.name.length);
}

/** A stored body split at its `<@user_id>` tokens. */
export function bodyParts(body: string): BodyPart[] {
  const parts: BodyPart[] = [];
  let end = 0;
  for (const match of body.matchAll(TOKEN)) {
    if (match.index > end) {
      parts.push({ kind: 'text', text: body.slice(end, match.index) });
    }
    parts.push({ kind: 'mention', userId: match[1] ?? '' });
    end = match.index + match[0].length;
  }
  if (end < body.length) {
    parts.push({ kind: 'text', text: body.slice(end) });
  }
  return parts;
}

function displayName(comment: Comment, userId: string): string {
  return (
    comment.mentions.find((m) => m.user_id.toLowerCase() === userId.toLowerCase())?.display_name ??
    'A former member'
  );
}

/** The comment's text with each mention as `@Name`, for a one-line preview. */
export function readableBody(comment: Comment): string {
  return bodyParts(comment.body ?? '')
    .map((part) => (part.kind === 'text' ? part.text : shownAs(displayName(comment, part.userId))))
    .join('');
}

/** A stored comment as its author edits it again. */
export function editableText(comment: Comment): MentionText {
  return {
    text: readableBody(comment),
    picked: comment.mentions.map((m) => ({ userId: m.user_id, name: m.display_name })),
  };
}

/** What the API stores: each `@Name` still in the text becomes a token. Others stay plain text. */
export function encodeMentions({ text, picked }: MentionText): string {
  return longestFirst(picked).reduce(
    (body, person) => body.replaceAll(shownAs(person.name), `<@${person.userId}>`),
    text,
  );
}

/** The text cut at each mention, for highlighting them. */
export function highlightParts({
  text,
  picked,
}: MentionText): { text: string; mention: boolean }[] {
  const parts: { text: string; mention: boolean }[] = [];
  let rest = text;
  const names = longestFirst(picked).map((person) => shownAs(person.name));
  while (rest !== '') {
    const next = names
      .map((name) => ({ name, at: rest.indexOf(name) }))
      .filter(({ at }) => at !== -1)
      .sort((a, b) => a.at - b.at)[0];
    if (!next) {
      parts.push({ text: rest, mention: false });
      break;
    }
    if (next.at > 0) {
      parts.push({ text: rest.slice(0, next.at), mention: false });
    }
    parts.push({ text: next.name, mention: true });
    rest = rest.slice(next.at + next.name.length);
  }
  return parts;
}

/** The `@query` being typed at the caret, if there is one. A finished mention is not a query. */
export function queryAtCaret(
  { text, picked }: MentionText,
  caret: number,
): { start: number; query: string } | null {
  const before = text.slice(0, caret);
  const start = before.lastIndexOf('@');
  if (start === -1 || (start > 0 && !/\s/.test(before.charAt(start - 1)))) {
    return null;
  }
  if (picked.some((person) => before.startsWith(shownAs(person.name), start))) {
    return null;
  }
  const query = before.slice(start + 1);
  return query.length > LONGEST_QUERY || query.includes('\n') ? null : { start, query };
}

/** The text with the query at `start` replaced by the person's mention, and the caret after it. */
export function insertMention(
  value: MentionText,
  start: number,
  caret: number,
  person: PickedMention,
): { value: MentionText; caret: number } {
  const inserted = `${shownAs(person.name)} `;
  return {
    value: {
      text: value.text.slice(0, start) + inserted + value.text.slice(caret),
      picked: value.picked.some((p) => p.userId === person.userId)
        ? value.picked
        : [...value.picked, person],
    },
    caret: start + inserted.length,
  };
}

/** Backspace right after a mention takes all of it; null when the caret is after anything else. */
export function removeMentionBefore(
  value: MentionText,
  caret: number,
): { value: MentionText; caret: number } | null {
  const before = value.text.slice(0, caret);
  const person = longestFirst(value.picked).find((p) => before.endsWith(shownAs(p.name)));
  if (!person) {
    return null;
  }
  const start = caret - shownAs(person.name).length;
  const text = value.text.slice(0, start) + value.text.slice(caret);
  return {
    value: {
      text,
      picked: text.includes(shownAs(person.name))
        ? value.picked
        : value.picked.filter((p) => p.userId !== person.userId),
    },
    caret: start,
  };
}

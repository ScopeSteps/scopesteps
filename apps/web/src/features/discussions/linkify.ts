export type TextPart = { kind: 'text'; text: string } | { kind: 'link'; text: string };

// Only web addresses become links; anything else, `javascript:` included, stays text.
const URL_PATTERN = /\bhttps?:\/\/[^\s<>"']+[^\s<>"'.,;:!?)\]]/giu;

/** Splits plain text into text and web addresses, so links can be made clickable without
 * ever rendering the text as HTML. */
export function linkify(text: string): TextPart[] {
  const parts: TextPart[] = [];
  let last = 0;
  for (const match of text.matchAll(URL_PATTERN)) {
    if (match.index > last) {
      parts.push({ kind: 'text', text: text.slice(last, match.index) });
    }
    parts.push({ kind: 'link', text: match[0] });
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    parts.push({ kind: 'text', text: text.slice(last) });
  }
  return parts;
}

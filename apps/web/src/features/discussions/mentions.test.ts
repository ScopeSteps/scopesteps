import { describe, expect, it } from 'vitest';

import {
  bodyParts,
  encodeMentions,
  highlightParts,
  insertMention,
  queryAtCaret,
  removeMentionBefore,
} from './mentions';

const SAM = { userId: '019a3a5e-0000-7000-8000-0000000000c1', name: 'Sam' };
const SAM_OKAFOR = { userId: '019a3a5e-0000-7000-8000-0000000000c2', name: 'Sam Okafor' };

describe('mentions in a comment', () => {
  it('splits a stored body at its tokens', () => {
    expect(bodyParts(`Hi <@${SAM.userId}>!`)).toEqual([
      { kind: 'text', text: 'Hi ' },
      { kind: 'mention', userId: SAM.userId },
      { kind: 'text', text: '!' },
    ]);
  });

  it('leaves text that only looks like a token alone', () => {
    expect(bodyParts('<@nobody>')).toEqual([{ kind: 'text', text: '<@nobody>' }]);
  });

  it('encodes each name still in the text, the longest name first', () => {
    const body = encodeMentions({ text: '@Sam Okafor and @Sam', picked: [SAM, SAM_OKAFOR] });

    expect(body).toBe(`<@${SAM_OKAFOR.userId}> and <@${SAM.userId}>`);
  });

  it('keeps a name the person broke while typing as plain text', () => {
    expect(encodeMentions({ text: '@Sa', picked: [SAM] })).toBe('@Sa');
  });

  it.each([
    ['hello @sa', 9, { start: 6, query: 'sa' }],
    ['@', 1, { start: 0, query: '' }],
    ['@Sam Oka', 8, { start: 0, query: 'Sam Oka' }],
    ['me@example.test', 15, null],
    ['no at sign', 5, null],
    ['@sam\nnext', 9, null],
  ])('finds the query in %j at %i', (text, caret, expected) => {
    expect(queryAtCaret({ text, picked: [] }, caret)).toEqual(expected);
  });

  it('does not take a finished mention, or what follows it, for a query', () => {
    expect(queryAtCaret({ text: '@Sam ', picked: [SAM] }, 5)).toBeNull();
    expect(queryAtCaret({ text: '@Sam hello', picked: [SAM] }, 10)).toBeNull();
  });

  it('inserts a mention over the query, with a space after it', () => {
    const { value, caret } = insertMention({ text: 'hi @sa!', picked: [] }, 3, 6, SAM);

    expect(value).toEqual({ text: 'hi @Sam !', picked: [SAM] });
    expect(caret).toBe(8);
  });

  it('removes a whole mention on Backspace, and forgets the person', () => {
    const removed = removeMentionBefore({ text: 'hi @Sam', picked: [SAM] }, 7);

    expect(removed).toEqual({ value: { text: 'hi ', picked: [] }, caret: 3 });
  });

  it('leaves Backspace alone anywhere else', () => {
    expect(removeMentionBefore({ text: 'hi @Sam ', picked: [SAM] }, 8)).toBeNull();
  });

  it('marks each mention for the highlight behind the text', () => {
    expect(highlightParts({ text: 'a @Sam b', picked: [SAM] })).toEqual([
      { text: 'a ', mention: false },
      { text: '@Sam', mention: true },
      { text: ' b', mention: false },
    ]);
  });
});

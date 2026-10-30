import { describe, expect, it } from 'vitest';

import { linkify } from './linkify';

describe('linkify', () => {
  it('splits out web addresses and leaves trailing punctuation as text', () => {
    expect(linkify('See https://example.test/a?b=1, then http://x.test.')).toEqual([
      { kind: 'text', text: 'See ' },
      { kind: 'link', text: 'https://example.test/a?b=1' },
      { kind: 'text', text: ', then ' },
      { kind: 'link', text: 'http://x.test' },
      { kind: 'text', text: '.' },
    ]);
  });

  it('never makes a link of anything but a web address', () => {
    expect(linkify('javascript:alert(1) <a href="https://x.test">x</a>')).toEqual([
      { kind: 'text', text: 'javascript:alert(1) <a href="' },
      { kind: 'link', text: 'https://x.test' },
      { kind: 'text', text: '">x</a>' },
    ]);
  });

  it('keeps text without addresses whole', () => {
    expect(linkify('Plain words')).toEqual([{ kind: 'text', text: 'Plain words' }]);
  });
});

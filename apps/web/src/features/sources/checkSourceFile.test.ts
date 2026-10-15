import { describe, expect, it } from 'vitest';

import { checkSourceFile } from './checkSourceFile';

const LIMITS = { max_bytes: 10, max_words: 6000 };

describe('checkSourceFile', () => {
  it.each([
    ['a .txt file', new File(['hello'], 'notes.txt'), null],
    ['a .md file', new File(['hello'], 'brief.md'), null],
    ['a .markdown file in capitals', new File(['hello'], 'BRIEF.MARKDOWN'), null],
    ['a file exactly at the limit', new File(['0123456789'], 'full.md'), null],
    ['a PDF', new File(['hello'], 'brief.pdf'), 'brief.pdf is not a .txt or .md file.'],
    [
      'a file with no extension',
      new File(['hello'], 'README'),
      'README is not a .txt or .md file.',
    ],
    ['an empty file', new File([], 'empty.txt'), 'empty.txt is empty.'],
    [
      'a file over the limit',
      new File(['01234567890'], 'big.md'),
      'big.md is larger than 10 bytes.',
    ],
  ])('answers %s', (_case, file, expected) => {
    expect(checkSourceFile(file, LIMITS)).toBe(expected);
  });

  it('leaves the size to the server until the limits have loaded', () => {
    expect(checkSourceFile(new File(['x'.repeat(100)], 'big.md'), undefined)).toBeNull();
  });
});

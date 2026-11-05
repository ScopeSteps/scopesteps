import { describe, expect, it } from 'vitest';

import { checkSourceFile } from './checkSourceFile';

const LIMITS = { max_bytes: 10, max_document_bytes: 20, max_words: 6000 };

describe('checkSourceFile', () => {
  it.each([
    ['a .txt file', new File(['hello'], 'notes.txt'), null],
    ['a .md file', new File(['hello'], 'brief.md'), null],
    ['a .markdown file in capitals', new File(['hello'], 'BRIEF.MARKDOWN'), null],
    ['a file exactly at the limit', new File(['0123456789'], 'full.md'), null],
    ['a Word file', new File(['PK'], 'brief.docx'), null],
    ['a PDF', new File(['%PDF'], 'BRIEF.PDF'), null],
    ['a WebVTT transcript', new File(['WEBVTT'], 'kickoff.vtt'), null],
    [
      'a document over the text limit but within its own',
      new File(['x'.repeat(15)], 'brief.pdf'),
      null,
    ],
    [
      'a document over its own limit',
      new File(['x'.repeat(21)], 'brief.docx'),
      'brief.docx is larger than 20 bytes.',
    ],
    [
      'an old Word file',
      new File(['hello'], 'brief.doc'),
      'brief.doc is not a .txt, .md, .docx, .pdf or .vtt file.',
    ],
    [
      'a file with no extension',
      new File(['hello'], 'README'),
      'README is not a .txt, .md, .docx, .pdf or .vtt file.',
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

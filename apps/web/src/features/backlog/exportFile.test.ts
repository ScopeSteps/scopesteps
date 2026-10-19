import { describe, expect, it } from 'vitest';

import { attachmentFilename, jiraRows, parseCsv } from './exportFile';

const HEADER = 'Issue ID,Issue Type,Summary,Description,Parent\r\n';

describe('parseCsv', () => {
  it('reads RFC 4180 rows: quoted commas, doubled quotes and line breaks inside cells', () => {
    const text = 'a,"b, c","say ""hi""","line one\nline two\r\nline three",\r\n1,2,3,4,5\r\n';

    expect(parseCsv(text)).toEqual([
      ['a', 'b, c', 'say "hi"', 'line one\nline two\r\nline three', ''],
      ['1', '2', '3', '4', '5'],
    ]);
  });

  it('keeps non-Latin text and a last row without a line break', () => {
    expect(parseCsv('予約,회의실\r\nx,y')).toEqual([
      ['予約', '회의실'],
      ['x', 'y'],
    ]);
  });

  it('refuses text with a quote that is never closed', () => {
    expect(parseCsv('a,"b\r\n')).toBeNull();
  });

  it('reads nothing from empty text', () => {
    expect(parseCsv('')).toEqual([]);
  });
});

describe('jiraRows', () => {
  it('maps each row of the five Jira columns, keeping every cell as the file holds it', () => {
    const text = `${HEADER}1,Epic,Room booking,Booking rooms.,\r\n2,Story,'=SUM(A1),"- one\n- two",1\r\n`;

    expect(jiraRows(text)).toEqual([
      {
        issueId: '1',
        issueType: 'Epic',
        summary: 'Room booking',
        description: 'Booking rooms.',
        parent: '',
      },
      {
        issueId: '2',
        issueType: 'Story',
        summary: "'=SUM(A1)",
        description: '- one\n- two',
        parent: '1',
      },
    ]);
  });

  it('reads a file with only its header as no rows', () => {
    expect(jiraRows(HEADER)).toEqual([]);
  });

  it.each([
    ['another header', 'Summary,Issue Type\r\nx,Epic\r\n'],
    ['a short row', `${HEADER}1,Epic,Room booking\r\n`],
    ['a long row', `${HEADER}1,Epic,Room booking,,,extra\r\n`],
    ['an open quote', `${HEADER}1,Epic,"Room booking,,\r\n`],
    ['no text', ''],
  ])('refuses %s', (_case, text) => {
    expect(jiraRows(text)).toBeNull();
  });
});

describe('attachmentFilename', () => {
  it('reads the quoted file name from Content-Disposition', () => {
    expect(attachmentFilename('attachment; filename="room-booking-backlog-v2.csv"')).toBe(
      'room-booking-backlog-v2.csv',
    );
  });

  it('is null without a header', () => {
    expect(attachmentFilename(null)).toBeNull();
  });
});

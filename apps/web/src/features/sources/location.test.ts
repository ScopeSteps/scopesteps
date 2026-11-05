import { describe, expect, it } from 'vitest';

import { blockLocation, formatMeetingTime } from './location';

describe('formatMeetingTime', () => {
  it.each([
    [0, '00:00:00'],
    [872_120, '00:14:32'],
    [3_723_999, '01:02:03'],
  ])('writes %i ms as %s', (milliseconds, written) => {
    expect(formatMeetingTime(milliseconds)).toBe(written);
  });
});

describe('blockLocation', () => {
  it('names the page of a PDF paragraph and the time of a transcript paragraph', () => {
    expect(blockLocation({ page: 4, start_ms: null })).toBe('page 4');
    expect(blockLocation({ page: null, start_ms: 872_120 })).toBe('00:14:32');
    expect(blockLocation({ page: null, start_ms: null })).toBeNull();
  });
});

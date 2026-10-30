import { describe, expect, it } from 'vitest';

import { formatRelative } from './formatWhen';

const NOW = new Date('2026-10-29T12:00:00Z');

describe('formatRelative', () => {
  it.each([
    ['2026-10-29T11:59:30Z', /seconds? ago|now/],
    ['2026-10-29T10:00:00Z', /2 hours ago/],
    ['2026-10-28T12:00:00Z', /yesterday|1 day ago/],
    ['2026-10-01T12:00:00Z', /4 weeks ago/],
    ['2025-10-29T12:00:00Z', /last year|1 year ago|12 months ago/],
  ])('says how long ago %s was', (iso, expected) => {
    expect(formatRelative(iso, NOW)).toMatch(expected);
  });
});

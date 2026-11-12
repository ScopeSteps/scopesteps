import { describe, expect, it } from 'vitest';

import { coveredPercent, formatWait } from './dashboard';

describe('formatWait', () => {
  it.each([
    [30, 'under a minute'],
    [60, '1 minute'],
    [45 * 60, '45 minutes'],
    [3600, '1 hour'],
    [47 * 3600, '47 hours'],
    [2 * 86400, '2 days'],
    [10.4 * 86400, '10 days'],
  ])('says %i seconds as “%s”', (seconds, words) => {
    expect(formatWait(seconds)).toBe(words);
  });
});

describe('coveredPercent', () => {
  it('rounds down, so nearly everything never reads as everything', () => {
    expect(coveredPercent(199, 200)).toBe(99);
  });

  it('counts nothing to cover as fully covered', () => {
    expect(coveredPercent(0, 0)).toBe(100);
  });
});

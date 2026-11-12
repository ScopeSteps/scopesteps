import type { components } from '@scopesteps/api-client';

export type Dashboard = components['schemas']['DashboardResponse'];

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

function count(value: number, unit: string): string {
  return `${String(value)} ${unit}${value === 1 ? '' : 's'}`;
}

/** A wait in plain words: "under a minute", "45 minutes", "5 hours", "3 days". */
export function formatWait(seconds: number): string {
  if (seconds < MINUTE) {
    return 'under a minute';
  }
  if (seconds < HOUR) {
    return count(Math.round(seconds / MINUTE), 'minute');
  }
  if (seconds < 2 * DAY) {
    return count(Math.round(seconds / HOUR), 'hour');
  }
  return count(Math.round(seconds / DAY), 'day');
}

/** The share covered, rounded down so 99.6% never reads as all of it. */
export function coveredPercent(covered: number, confirmed: number): number {
  return confirmed === 0 ? 100 : Math.floor((covered / confirmed) * 100);
}

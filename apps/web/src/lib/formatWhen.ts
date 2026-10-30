const WHEN = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });

/** A moment from the API as every screen writes it, in the reader's locale: "Oct 15, 2026, 6:35 PM". */
export function formatWhen(iso: string): string {
  return WHEN.format(new Date(iso));
}

const RELATIVE = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
const STEPS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['second', 60],
  ['minute', 60],
  ['hour', 24],
  ['day', 7],
  ['week', 4.35],
  ['month', 12],
];

/** How long ago a moment from the API was, in the reader's locale: "2 hours ago", "yesterday". */
export function formatRelative(iso: string, now: Date = new Date()): string {
  let value = (new Date(iso).getTime() - now.getTime()) / 1000;
  for (const [unit, size] of STEPS) {
    if (Math.abs(value) < size) {
      return RELATIVE.format(Math.round(value), unit);
    }
    value /= size;
  }
  return RELATIVE.format(Math.round(value), 'year');
}

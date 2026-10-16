const WHEN = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });

/** A moment from the API as every screen writes it, in the reader's locale: "Oct 15, 2026, 6:35 PM". */
export function formatWhen(iso: string): string {
  return WHEN.format(new Date(iso));
}

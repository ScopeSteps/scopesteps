/** A moment as the reader's locale writes it, machine-readable too. */
export function Time({ at }: { at: string }) {
  return <time dateTime={at}>{new Date(at).toLocaleString()}</time>;
}

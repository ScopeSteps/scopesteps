const KIB = 1024;

/** A byte limit as people read it: 524288 is "512 KB". */
export function formatBytes(bytes: number): string {
  if (bytes >= KIB * KIB) {
    return `${(bytes / (KIB * KIB)).toLocaleString(undefined, { maximumFractionDigits: 1 })} MB`;
  }
  if (bytes >= KIB) {
    return `${(bytes / KIB).toLocaleString(undefined, { maximumFractionDigits: 1 })} KB`;
  }
  return `${bytes.toLocaleString()} bytes`;
}

export function formatAddedAt(isoDate: string): string {
  return new Date(isoDate).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function plural(count: number, noun: string, pluralNoun = `${noun}s`): string {
  return `${count.toLocaleString()} ${count === 1 ? noun : pluralNoun}`;
}

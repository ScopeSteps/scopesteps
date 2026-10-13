type ClassValue = string | false | null | undefined;

/** Joins class names, skipping the falsy ones, so conditional classes read as `a && 'b'`. */
export function cx(...values: ClassValue[]): string {
  return values.filter(Boolean).join(' ');
}

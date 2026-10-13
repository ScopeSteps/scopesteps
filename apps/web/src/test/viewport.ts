/**
 * jsdom has no `matchMedia`. This makes every media query match or not, which is enough to
 * put the shell in its drawer layout. Undo it with `resetViewport` after the test.
 */
export function setNarrowViewport(narrow: boolean): void {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: (query: string) => ({
      matches: narrow,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }),
  });
}

export function resetViewport(): void {
  Reflect.deleteProperty(window, 'matchMedia');
}

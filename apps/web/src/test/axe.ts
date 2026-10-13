import axe from 'axe-core';
import { expect } from 'vitest';

/**
 * Runs the automated accessibility rules over the whole document, so portalled layers are
 * included. jsdom has no layout, so colour contrast is not checked here.
 */
export async function expectNoAccessibilityViolations(): Promise<void> {
  const results = await axe.run(document.body, {
    rules: { 'color-contrast': { enabled: false } },
  });
  expect(results.violations.map((violation) => `${violation.id}: ${violation.help}`)).toEqual([]);
}

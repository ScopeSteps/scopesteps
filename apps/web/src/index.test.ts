import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

// Read from disk: Vitest replaces imported stylesheets with an empty module, and Vite turns
// `new URL('./index.css', import.meta.url)` into an asset address.
const css = readFileSync(fileURLToPath(import.meta.url).replace(/\.test\.ts$/, '.css'), 'utf8');

function declarations(block: string): string[] {
  return block
    .split(';')
    .map((declaration) => declaration.replace(/\s+/g, ' ').trim())
    .filter(
      (declaration) => declaration.startsWith('--') || declaration.startsWith('color-scheme'),
    );
}

function blockAfter(selector: string): string[] {
  const start = css.indexOf(selector);
  if (start === -1) {
    throw new Error(`index.css has no "${selector}" block`);
  }
  const open = css.indexOf('{', start);
  return declarations(css.slice(open + 1, css.indexOf('}', open)));
}

function names(block: string[]): string[] {
  return block.map((declaration) => declaration.split(':')[0] ?? '');
}

describe('design tokens', () => {
  const light = blockAfter(":root,\n[data-theme='light']");
  const systemDark = blockAfter(":root:not([data-theme='light'])");
  const chosenDark = blockAfter("[data-theme='dark']");

  it('gives the dark theme the same values whether the device or the user picked it', () => {
    expect(systemDark).toEqual(chosenDark);
  });

  it('gives every token a value in both themes', () => {
    expect(light.length).toBeGreaterThan(30);
    expect(names(chosenDark)).toEqual(names(light));
  });

  it('defines both accents from the same set of roles', () => {
    const roles = (accent: string) =>
      blockAfter(`[data-accent='${accent}']`).map((declaration) =>
        declaration.replaceAll(accent, 'ACCENT'),
      );

    expect(roles('teal')).toEqual(roles('indigo'));
    expect(roles('indigo')).toHaveLength(6);
  });
});

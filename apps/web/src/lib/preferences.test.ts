import { beforeEach, describe, expect, it } from 'vitest';

import {
  applyAppearance,
  DEFAULT_PREFERENCES,
  loadPreferences,
  savePreferences,
} from '@/lib/preferences';

beforeEach(() => {
  window.localStorage.clear();
});

describe('preferences', () => {
  it('follows the device theme with the indigo accent until the user chooses', () => {
    expect(loadPreferences()).toEqual(DEFAULT_PREFERENCES);
    expect(DEFAULT_PREFERENCES).toEqual({
      theme: 'system',
      accent: 'indigo',
      sidebarCollapsed: false,
    });
  });

  it('restores what was saved', () => {
    savePreferences({ theme: 'dark', accent: 'teal', sidebarCollapsed: true });

    expect(loadPreferences()).toEqual({ theme: 'dark', accent: 'teal', sidebarCollapsed: true });
  });

  it.each([
    ['text that is not JSON', 'not json'],
    ['a value that is not an object', '42'],
    ['unknown choices', JSON.stringify({ theme: 'sepia', accent: 'pink', sidebarCollapsed: 1 })],
  ])('falls back to the defaults for %s', (_case, stored) => {
    window.localStorage.setItem('scopesteps:preferences', stored);

    expect(loadPreferences()).toEqual(DEFAULT_PREFERENCES);
  });

  it('sets the attributes the design tokens key on', () => {
    const root = document.createElement('html');

    applyAppearance({ theme: 'dark', accent: 'teal' }, root);
    expect(root.dataset).toMatchObject({ theme: 'dark', accent: 'teal' });

    applyAppearance({ theme: 'system', accent: 'indigo' }, root);
    expect(root).not.toHaveAttribute('data-theme');
    expect(root.dataset.accent).toBe('indigo');
  });
});

export const THEMES = ['light', 'dark', 'system'] as const;
export const ACCENTS = ['indigo', 'teal'] as const;

export type Theme = (typeof THEMES)[number];
export type Accent = (typeof ACCENTS)[number];

/** What this browser remembers about how the app looks. Never project data or profiles. */
export interface Preferences {
  theme: Theme;
  accent: Accent;
  sidebarCollapsed: boolean;
}

export const DEFAULT_PREFERENCES: Preferences = {
  theme: 'system',
  accent: 'indigo',
  sidebarCollapsed: false,
};

const STORAGE_KEY = 'scopesteps:preferences';

function isOneOf<T extends string>(options: readonly T[], value: unknown): value is T {
  return options.some((option) => option === value);
}

/** Reads the stored preferences; anything missing or unrecognised falls back to the default. */
export function loadPreferences(): Preferences {
  let stored: unknown;
  try {
    stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? 'null');
  } catch {
    // Storage can be unavailable (private mode) or hold something that is not JSON.
    return DEFAULT_PREFERENCES;
  }
  if (typeof stored !== 'object' || stored === null) {
    return DEFAULT_PREFERENCES;
  }
  return {
    theme: 'theme' in stored && isOneOf(THEMES, stored.theme) ? stored.theme : 'system',
    accent: 'accent' in stored && isOneOf(ACCENTS, stored.accent) ? stored.accent : 'indigo',
    sidebarCollapsed: 'sidebarCollapsed' in stored && stored.sidebarCollapsed === true,
  };
}

export function savePreferences(preferences: Preferences): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  } catch {
    // The choice still applies to this page; it is just not remembered.
  }
}

/** Sets the attributes the design tokens key on. No `data-theme` means "follow the device". */
export function applyAppearance(
  { theme, accent }: Pick<Preferences, 'theme' | 'accent'>,
  root: HTMLElement = document.documentElement,
): void {
  if (theme === 'system') {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = theme;
  }
  root.dataset.accent = accent;
}

import { createContext, useContext } from 'react';

import type { Preferences } from '@/lib/preferences';

interface PreferencesContextValue {
  preferences: Preferences;
  updatePreferences: (change: Partial<Preferences>) => void;
}

export const PreferencesContext = createContext<PreferencesContextValue | null>(null);

export function usePreferences(): PreferencesContextValue {
  const value = useContext(PreferencesContext);
  if (!value) {
    throw new Error('usePreferences needs a PreferencesProvider above it');
  }
  return value;
}

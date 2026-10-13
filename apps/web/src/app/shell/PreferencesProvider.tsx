import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { applyAppearance, loadPreferences, savePreferences } from '@/lib/preferences';
import type { Preferences } from '@/lib/preferences';

import { PreferencesContext } from './preferencesContext';

interface PreferencesProviderProps {
  children: ReactNode;
}

/** Holds the theme, accent and sidebar state, applies them and remembers them in this browser. */
export function PreferencesProvider({ children }: PreferencesProviderProps) {
  const [preferences, setPreferences] = useState(loadPreferences);
  const updatePreferences = useCallback((change: Partial<Preferences>) => {
    setPreferences((current) => ({ ...current, ...change }));
  }, []);

  useEffect(() => {
    applyAppearance(preferences);
    savePreferences(preferences);
  }, [preferences]);

  const value = useMemo(
    () => ({ preferences, updatePreferences }),
    [preferences, updatePreferences],
  );
  return <PreferencesContext value={value}>{children}</PreferencesContext>;
}

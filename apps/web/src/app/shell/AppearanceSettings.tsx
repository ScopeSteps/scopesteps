import { Icon } from '@/components/Icon';
import type { IconName } from '@/components/Icon';
import type { Accent, Theme } from '@/lib/preferences';

import { OptionCard } from './OptionCard';
import { usePreferences } from './preferencesContext';
import { ThemePreview } from './ThemePreview';

const THEME_OPTIONS: readonly { value: Theme; label: string; icon: IconName }[] = [
  { value: 'light', label: 'Light', icon: 'sun' },
  { value: 'dark', label: 'Dark', icon: 'moon' },
  { value: 'system', label: 'System', icon: 'monitor' },
];

const ACCENT_OPTIONS: readonly { value: Accent; label: string }[] = [
  { value: 'indigo', label: 'Indigo' },
  { value: 'teal', label: 'Teal' },
];

export function AppearanceSettings() {
  const { preferences, updatePreferences } = usePreferences();

  return (
    <>
      <h3 className="text-[15px] font-semibold">Appearance</h3>
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 text-[13px] font-semibold">Theme</legend>
        <div className="grid grid-cols-3 gap-2.5 max-wide:grid-cols-2">
          {THEME_OPTIONS.map((option) => (
            <OptionCard
              key={option.value}
              name="theme"
              value={option.value}
              checked={preferences.theme === option.value}
              onSelect={() => {
                updatePreferences({ theme: option.value });
              }}
            >
              <ThemePreview theme={option.value} />
              <span className="flex items-center gap-1.5">
                <Icon name={option.icon} size={16} />
                {option.label}
              </span>
            </OptionCard>
          ))}
        </div>
        <span className="text-xs font-normal text-subtle">System follows your device setting.</span>
      </fieldset>
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 text-[13px] font-semibold">Accent color</legend>
        <div className="grid grid-cols-3 gap-2.5 max-wide:grid-cols-2">
          {ACCENT_OPTIONS.map((option) => (
            <OptionCard
              key={option.value}
              name="accent"
              value={option.value}
              checked={preferences.accent === option.value}
              onSelect={() => {
                updatePreferences({ accent: option.value });
              }}
            >
              <span className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  data-accent={option.value}
                  className="size-[22px] flex-none rounded-full bg-accent"
                />
                {option.label}
              </span>
            </OptionCard>
          ))}
        </div>
        <span className="text-xs font-normal text-subtle">
          Used for buttons, links and highlights. Status colors stay the same so warnings always
          read the same way.
        </span>
      </fieldset>
    </>
  );
}

import { useState } from 'react';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { describeError } from '@/lib/apiError';

import type { NotificationSettings } from './types';
import { useNotificationSettings, useSaveNotificationSettings } from './useNotifications';

const CHOICES: readonly { key: keyof NotificationSettings; label: string }[] = [
  { key: 'email_on_mention', label: 'Email me when I’m mentioned' },
  { key: 'email_on_reply', label: 'Email me about replies to threads I follow' },
];

/** Which notifications also come by email, saved as soon as a box is changed. */
export function NotificationPreferences() {
  const settings = useNotificationSettings();
  const save = useSaveNotificationSettings();
  // Shown at once, so the box does not flip back while the save is on its way.
  const [saving, setSaving] = useState<NotificationSettings | null>(null);

  return (
    <section aria-label="Email notifications" className="flex flex-col gap-2">
      <h3 className="text-[15px] font-semibold">Email notifications</h3>
      {settings.isPending ? (
        <p role="status" className="text-muted">
          Loading your choices…
        </p>
      ) : settings.error ? (
        <Banner
          tone="bad"
          role="alert"
          action={
            <Button size="sm" onClick={() => void settings.refetch()}>
              Try again
            </Button>
          }
        >
          Could not load your choices. {describeError(settings.error)}
        </Banner>
      ) : (
        <>
          {CHOICES.map(({ key, label }) => (
            <label key={key} className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={(saving ?? settings.data)[key]}
                disabled={save.isPending}
                onChange={(event) => {
                  const next = { ...settings.data, [key]: event.target.checked };
                  setSaving(next);
                  save.mutate(next, {
                    onSettled: () => {
                      setSaving(null);
                    },
                  });
                }}
                className="size-4 accent-[var(--accent)]"
              />
              {label}
            </label>
          ))}
          {save.error && (
            <Banner tone="bad" role="alert">
              Your choice was not saved. {describeError(save.error)}
            </Banner>
          )}
        </>
      )}
    </section>
  );
}

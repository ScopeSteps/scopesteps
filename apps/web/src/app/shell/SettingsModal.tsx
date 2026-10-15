import { useState } from 'react';

import { Icon } from '@/components/Icon';
import type { IconName } from '@/components/Icon';
import { Modal } from '@/components/Modal';
import { cx } from '@/lib/cx';

import { AccountSettings } from './AccountSettings';
import { AppearanceSettings } from './AppearanceSettings';

type Section = 'appearance' | 'account';

const SECTIONS: readonly { value: Section; label: string; icon: IconName }[] = [
  { value: 'appearance', label: 'Appearance', icon: 'sun' },
  { value: 'account', label: 'Account', icon: 'settings' },
];

interface SettingsModalProps {
  onClose: () => void;
}

/** The user's own settings. A section is added to the navigation by the work that delivers it. */
export function SettingsModal({ onClose }: SettingsModalProps) {
  const [section, setSection] = useState<Section>('appearance');

  return (
    <Modal title="Your settings" onClose={onClose} wide flush>
      <div className="grid min-h-0 flex-1 grid-cols-[180px_minmax(0,1fr)] max-wide:grid-cols-[minmax(0,1fr)] max-wide:grid-rows-[auto_minmax(0,1fr)]">
        <nav
          aria-label="Settings sections"
          className="flex flex-col gap-0.5 rounded-bl-[14px] border-r border-line bg-surface-2 p-2.5 max-wide:flex-row max-wide:overflow-x-auto max-wide:rounded-none max-wide:border-r-0 max-wide:border-b"
        >
          {SECTIONS.map((option) => {
            const current = option.value === section;
            return (
              <button
                key={option.value}
                type="button"
                aria-current={current ? 'page' : undefined}
                onClick={() => {
                  setSection(option.value);
                }}
                className={cx(
                  'flex min-h-9 cursor-pointer items-center gap-2.5 rounded-lg border px-2.5 text-left',
                  current
                    ? 'border-line bg-surface font-semibold text-fg'
                    : 'border-transparent font-medium text-muted hover:bg-hover hover:text-fg',
                )}
              >
                <Icon name={option.icon} size={16} />
                {option.label}
              </button>
            );
          })}
        </nav>
        <div className="flex flex-col gap-4 overflow-auto px-[22px] py-5">
          {section === 'appearance' ? <AppearanceSettings /> : <AccountSettings />}
        </div>
      </div>
    </Modal>
  );
}

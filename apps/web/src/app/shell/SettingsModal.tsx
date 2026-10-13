import { Icon } from '@/components/Icon';
import { Modal } from '@/components/Modal';

import { AppearanceSettings } from './AppearanceSettings';

interface SettingsModalProps {
  onClose: () => void;
}

/**
 * The user's own settings. Appearance is the only section so far; a section is added to the
 * navigation by the ticket that delivers it.
 */
export function SettingsModal({ onClose }: SettingsModalProps) {
  return (
    <Modal title="Your settings" onClose={onClose} wide flush>
      <div className="grid min-h-0 flex-1 grid-cols-[180px_minmax(0,1fr)] max-wide:grid-cols-[minmax(0,1fr)] max-wide:grid-rows-[auto_minmax(0,1fr)]">
        <nav
          aria-label="Settings sections"
          className="flex flex-col gap-0.5 rounded-bl-[14px] border-r border-line bg-surface-2 p-2.5 max-wide:flex-row max-wide:overflow-x-auto max-wide:rounded-none max-wide:border-r-0 max-wide:border-b"
        >
          <button
            type="button"
            aria-current="page"
            className="flex min-h-9 items-center gap-2.5 rounded-lg border border-line bg-surface px-2.5 text-left font-semibold text-fg"
          >
            <Icon name="sun" size={16} />
            Appearance
          </button>
        </nav>
        <div className="flex flex-col gap-4 overflow-auto px-[22px] py-5">
          <AppearanceSettings />
        </div>
      </div>
    </Modal>
  );
}

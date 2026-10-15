import { useRef } from 'react';
import type { KeyboardEvent, RefObject } from 'react';

import { Icon } from '@/components/Icon';
import { useLayer } from '@/components/useLayer';

interface AccountMenuItemsProps {
  name: string;
  email: string;
  /** The button that opened the menu; focus returns to it. */
  trigger: RefObject<HTMLElement | null>;
  onClose: () => void;
  onOpenSettings: () => void;
  onSignOut: () => void;
}

/** The open account menu: focus starts on its first item and arrow keys move between items. */
export function AccountMenuItems({
  name,
  email,
  trigger,
  onClose,
  onOpenSettings,
  onSignOut,
}: AccountMenuItemsProps) {
  const menu = useRef<HTMLDivElement>(null);
  const firstItem = useRef<HTMLButtonElement>(null);
  useLayer(menu, { onClose, initialFocus: firstItem, returnFocus: trigger, trapFocus: false });

  function moveFocus(event: KeyboardEvent) {
    const items = [...(menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];
    const current = items.findIndex((item) => item === document.activeElement);
    const step = event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0;
    if (step === 0 || items.length === 0) {
      return;
    }
    event.preventDefault();
    items.at((current + step) % items.length)?.focus();
  }

  return (
    <div
      ref={menu}
      role="menu"
      aria-label="Account"
      tabIndex={-1}
      onKeyDown={moveFocus}
      onBlur={(event) => {
        // Focus left the menu (Tab, or a click elsewhere): a menu does not stay open behind it.
        if (!event.currentTarget.contains(event.relatedTarget)) {
          onClose();
        }
      }}
      className="absolute inset-x-0 bottom-[58px] z-[25] flex flex-col rounded-xl border border-line bg-surface p-1.5 shadow-pop"
    >
      <div className="mb-1 flex flex-col border-b border-line px-2.5 pt-2 pb-2.5">
        <strong className="font-semibold">{name}</strong>
        <span className="text-xs break-all text-subtle">{email}</span>
      </div>
      <button
        ref={firstItem}
        type="button"
        role="menuitem"
        onClick={onOpenSettings}
        className="flex min-h-9 cursor-pointer items-center gap-2.5 rounded-lg px-2.5 text-left hover:bg-hover"
      >
        <Icon name="settings" />
        Settings
      </button>
      <button
        type="button"
        role="menuitem"
        onClick={onSignOut}
        className="flex min-h-9 cursor-pointer items-center gap-2.5 rounded-lg px-2.5 text-left hover:bg-hover"
      >
        <Icon name="logout" />
        Sign out
      </button>
    </div>
  );
}

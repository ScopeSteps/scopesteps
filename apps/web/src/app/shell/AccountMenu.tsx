import { useRef, useState } from 'react';

import { Avatar } from '@/components/Avatar';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { useCurrentUser } from '@/features/identity';
import { describeError } from '@/lib/apiError';

import { AccountMenuItems } from './AccountMenuItems';
import { useSignOutOfApp } from './useSignOutOfApp';

interface AccountMenuProps {
  /** The user's role in the project in view, when there is one. */
  roleLabel: string | null;
  onOpenSettings: () => void;
}

/** The signed-in user, as `GET /me` returns them, with the menu that opens their settings. */
export function AccountMenu({ roleLabel, onOpenSettings }: AccountMenuProps) {
  const { data: user, isPending, refetch } = useCurrentUser();
  const signOut = useSignOutOfApp();
  const [menuOpen, setMenuOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);

  if (isPending) {
    return (
      <p role="status" className="min-h-12 p-2 text-[13px] text-subtle">
        Loading your account…
      </p>
    );
  }
  if (!user) {
    return (
      <div role="alert" className="flex min-h-12 flex-col items-start gap-1 p-2 text-[13px]">
        <span className="text-bad-ink">Could not load your account.</span>
        <Button size="sm" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  return (
    <div className="relative">
      {menuOpen && (
        <AccountMenuItems
          name={user.display_name}
          email={user.email}
          trigger={trigger}
          onClose={() => {
            setMenuOpen(false);
          }}
          onOpenSettings={() => {
            setMenuOpen(false);
            onOpenSettings();
          }}
          onSignOut={() => {
            setMenuOpen(false);
            signOut.mutate();
          }}
        />
      )}
      {signOut.isPending && (
        <p role="status" className="px-2 pb-1 text-[13px] text-subtle">
          Signing out…
        </p>
      )}
      {signOut.error && (
        <p role="alert" className="px-2 pb-1 text-[13px] text-bad-ink">
          Could not sign out. {describeError(signOut.error)}
        </p>
      )}
      <button
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        // The menu closes itself when focus leaves it; without this the same click reopens it.
        onMouseDown={(event) => {
          if (menuOpen) {
            event.preventDefault();
          }
        }}
        onClick={() => {
          setMenuOpen((open) => !open);
        }}
        className="flex w-full cursor-pointer items-center gap-2.5 rounded-[10px] p-2 text-left hover:bg-hover"
      >
        <Avatar name={user.display_name} />
        <span className="flex min-w-0 flex-1 flex-col leading-tight">
          <strong className="truncate text-[13px] font-semibold">{user.display_name}</strong>
          {roleLabel && <span className="text-xs text-subtle">{roleLabel}</span>}
        </span>
        <span className="text-muted">
          <Icon name="up" size={16} />
        </span>
      </button>
    </div>
  );
}

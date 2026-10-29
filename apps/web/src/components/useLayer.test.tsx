import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrictMode, useRef, useState } from 'react';
import { describe, expect, it } from 'vitest';

import { useLayer } from './useLayer';

function Menu({ onClose }: { onClose: () => void }) {
  const menu = useRef<HTMLDivElement>(null);
  const item = useRef<HTMLButtonElement>(null);
  useLayer(menu, { onClose, initialFocus: item, trapFocus: false });
  return (
    <div
      ref={menu}
      role="menu"
      aria-label="Actions"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          onClose();
        }
      }}
    >
      <button ref={item} type="button" role="menuitem">
        Rename
      </button>
    </div>
  );
}

function MenuButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
      >
        Open
      </button>
      {open && (
        <Menu
          onClose={() => {
            setOpen(false);
          }}
        />
      )}
    </>
  );
}

/** A dialog whose field takes focus as it mounts, before the layer's effect runs. */
function FormDialog({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDivElement>(null);
  useLayer(dialog, { onClose });
  return (
    <div ref={dialog} role="dialog" aria-label="Form" tabIndex={-1}>
      <input
        aria-label="Email"
        ref={(node) => {
          node?.focus();
        }}
      />
    </div>
  );
}

function FormButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
      >
        Invite
      </button>
      {open && (
        <FormDialog
          onClose={() => {
            setOpen(false);
          }}
        />
      )}
    </>
  );
}

describe('useLayer', () => {
  it('returns focus to the opener when a field inside took focus as it mounted', async () => {
    render(
      <StrictMode>
        <FormButton />
      </StrictMode>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Invite' }));
    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('button', { name: 'Invite' })).toHaveFocus();
  });

  it('keeps focus in a layer when StrictMode runs its effect twice, and returns it on close', async () => {
    render(
      <StrictMode>
        <MenuButton />
      </StrictMode>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Open' }));

    expect(screen.getByRole('menu', { name: 'Actions' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Rename' })).toHaveFocus();

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open' })).toHaveFocus();
  });
});

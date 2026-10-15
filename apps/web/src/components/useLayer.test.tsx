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

describe('useLayer', () => {
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

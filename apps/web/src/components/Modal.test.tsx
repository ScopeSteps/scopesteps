import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { SideSheet } from '@/components/SideSheet';
import { expectNoAccessibilityViolations } from '@/test/axe';

function Example() {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  return (
    <main>
      <Button
        onClick={() => {
          setSheetOpen(true);
        }}
      >
        Show source
      </Button>
      <Button
        onClick={() => {
          setModalOpen(true);
        }}
      >
        Rename
      </Button>
      {sheetOpen && (
        <SideSheet
          title="Source"
          onClose={() => {
            setSheetOpen(false);
          }}
        >
          <Button
            onClick={() => {
              setModalOpen(true);
            }}
          >
            Rename from the sheet
          </Button>
        </SideSheet>
      )}
      {modalOpen && (
        <Modal
          title="Rename the source"
          onClose={() => {
            setModalOpen(false);
          }}
          footer={<Button variant="primary">Save</Button>}
        >
          <label>
            Name <input defaultValue="brief.md" />
          </label>
        </Modal>
      )}
    </main>
  );
}

describe('Modal', () => {
  it('moves focus to its title when it opens and names the dialog after it', async () => {
    render(<Example />);

    await userEvent.click(screen.getByRole('button', { name: 'Rename' }));

    const dialog = screen.getByRole('dialog', { name: 'Rename the source' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByRole('heading', { name: 'Rename the source' })).toHaveFocus();
    await expectNoAccessibilityViolations();
  });

  it('closes on Escape and returns focus to the control that opened it', async () => {
    render(<Example />);
    await userEvent.click(screen.getByRole('button', { name: 'Rename' }));

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rename' })).toHaveFocus();
  });

  it('closes from its close button and from the backdrop, not from a click inside', async () => {
    render(<Example />);
    await userEvent.click(screen.getByRole('button', { name: 'Rename' }));

    await userEvent.click(screen.getByRole('textbox', { name: 'Name' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Rename' }));
    const backdrop = screen.getByRole('dialog').parentElement;
    if (!backdrop) {
      throw new Error('The modal has no backdrop');
    }
    await userEvent.click(backdrop);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps Tab inside the modal in both directions', async () => {
    render(<Example />);
    await userEvent.click(screen.getByRole('button', { name: 'Rename' }));

    await userEvent.tab();
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole('button', { name: 'Save' })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(screen.getByRole('button', { name: 'Save' })).toHaveFocus();
  });

  it('closes only the top layer on Escape when it is open over a side sheet', async () => {
    render(<Example />);
    await userEvent.click(screen.getByRole('button', { name: 'Show source' }));
    await userEvent.click(screen.getByRole('button', { name: 'Rename from the sheet' }));
    expect(screen.getAllByRole('dialog')).toHaveLength(2);

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog', { name: 'Rename the source' })).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Source' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rename from the sheet' })).toHaveFocus();

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show source' })).toHaveFocus();
  });
});

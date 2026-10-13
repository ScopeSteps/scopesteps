import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { Button } from '@/components/Button';
import { SideSheet } from '@/components/SideSheet';
import { expectNoAccessibilityViolations } from '@/test/axe';

function Example() {
  const [open, setOpen] = useState(false);
  return (
    <main>
      <Button
        onClick={() => {
          setOpen(true);
        }}
      >
        Show evidence
      </Button>
      {open && (
        <SideSheet
          title="Evidence"
          onClose={() => {
            setOpen(false);
          }}
          footer={<Button>Open full source</Button>}
        >
          <blockquote>A booking can last up to 4 hours.</blockquote>
        </SideSheet>
      )}
    </main>
  );
}

describe('SideSheet', () => {
  it('opens as a dialog with focus on its title', async () => {
    render(<Example />);

    await userEvent.click(screen.getByRole('button', { name: 'Show evidence' }));

    expect(screen.getByRole('dialog', { name: 'Evidence' })).toHaveTextContent(
      'A booking can last up to 4 hours.',
    );
    expect(screen.getByRole('heading', { name: 'Evidence' })).toHaveFocus();
    await expectNoAccessibilityViolations();
  });

  it('closes on Escape and returns focus to the control that opened it', async () => {
    render(<Example />);
    await userEvent.click(screen.getByRole('button', { name: 'Show evidence' }));

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show evidence' })).toHaveFocus();
  });

  it('closes from its close button and keeps Tab inside while open', async () => {
    render(<Example />);
    await userEvent.click(screen.getByRole('button', { name: 'Show evidence' }));

    await userEvent.tab();
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole('button', { name: 'Open full source' })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();

    await userEvent.keyboard('{Enter}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

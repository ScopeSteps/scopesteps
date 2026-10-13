import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { SyntheticEvent } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { Button } from '@/components/Button';

describe('Button', () => {
  it('calls its handler when pressed with the keyboard', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Add source</Button>);

    screen.getByRole('button', { name: 'Add source' }).focus();
    await userEvent.keyboard('{Enter}');

    expect(onClick).toHaveBeenCalledOnce();
  });

  it('does not submit the form around it unless asked to', async () => {
    const onSubmit = vi.fn((event: SyntheticEvent) => {
      event.preventDefault();
    });
    render(
      <form onSubmit={onSubmit}>
        <Button>Cancel</Button>
        <Button type="submit" variant="primary">
          Save
        </Button>
      </form>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onSubmit).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it('ignores presses while disabled', async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Approve
      </Button>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }));

    expect(onClick).not.toHaveBeenCalled();
  });
});

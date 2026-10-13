import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { IconButton } from '@/components/IconButton';

describe('IconButton', () => {
  it('is named by its label and hides the icon from assistive technology', async () => {
    const onClick = vi.fn();
    render(<IconButton icon="close" label="Close" onClick={onClick} />);

    const button = screen.getByRole('button', { name: 'Close' });
    await userEvent.click(button);

    expect(onClick).toHaveBeenCalledOnce();
    expect(button).toHaveAttribute('title', 'Close');
    expect(button.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });
});

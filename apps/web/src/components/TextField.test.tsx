import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { TextField } from '@/components/TextField';
import { expectNoAccessibilityViolations } from '@/test/axe';

function Example({ rows, error }: { rows?: number; error?: string }) {
  const [value, setValue] = useState('');
  return (
    <main>
      <TextField
        label="Title"
        value={value}
        onChange={setValue}
        help="Up to 200 characters"
        maxLength={200}
        focusOnMount
        {...(rows === undefined ? {} : { rows })}
        {...(error === undefined ? {} : { error })}
      />
    </main>
  );
}

describe('TextField', () => {
  it('labels an input, describes it with its hint, and takes focus when asked', async () => {
    render(<Example />);

    const input = screen.getByRole('textbox', { name: 'Title' });
    expect(input.tagName).toBe('INPUT');
    expect(input).toHaveFocus();
    expect(input).toHaveAccessibleDescription('Up to 200 characters');
    await userEvent.type(input, 'Book a room');
    expect(input).toHaveValue('Book a room');
    await expectNoAccessibilityViolations();
  });

  it('renders a textarea and marks it invalid with its error', async () => {
    render(<Example rows={3} error="Enter a title." />);

    const textarea = screen.getByRole('textbox', { name: 'Title' });
    expect(textarea.tagName).toBe('TEXTAREA');
    expect(textarea).toBeInvalid();
    expect(textarea).toHaveAccessibleDescription('Up to 200 characters Enter a title.');
    await expectNoAccessibilityViolations();
  });
});

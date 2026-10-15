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

  it('is marked invalid by a message shown elsewhere, and can hold a control at its edge', async () => {
    render(
      <main>
        <TextField
          label="Code"
          type="password"
          autoComplete="one-time-code"
          value=""
          onChange={() => undefined}
          invalid
          describedBy="form-problem"
          trailing={<button type="button">Show</button>}
        />
        <p id="form-problem">That code has expired.</p>
      </main>,
    );

    const input = screen.getByLabelText('Code');
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveAttribute('autocomplete', 'one-time-code');
    expect(input).toBeInvalid();
    expect(input).toHaveAccessibleDescription('That code has expired.');
    expect(screen.getByRole('button', { name: 'Show' })).toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('shows a read-only value without needing a change handler', () => {
    render(<TextField label="Email" value="editor@scopesteps.local" readOnly />);

    expect(screen.getByRole('textbox', { name: 'Email' })).toHaveAttribute('readonly');
  });
});

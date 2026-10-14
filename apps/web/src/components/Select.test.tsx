import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Select } from '@/components/Select';

describe('Select', () => {
  it('is a native select that takes its label and reports the choice', async () => {
    const onChange = vi.fn();
    render(
      <label>
        Version
        <Select
          value="a"
          onChange={(event) => {
            onChange(event.currentTarget.value);
          }}
        >
          <option value="a">v1</option>
          <option value="b">v2</option>
        </Select>
      </label>,
    );

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Version' }), 'v2');

    expect(onChange).toHaveBeenCalledWith('b');
  });
});

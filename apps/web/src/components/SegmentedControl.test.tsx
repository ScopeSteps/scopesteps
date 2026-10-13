import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SegmentedControl } from '@/components/SegmentedControl';

const OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'attention', label: 'Needs attention' },
] as const;

describe('SegmentedControl', () => {
  it('marks the current option as pressed inside a named group', () => {
    render(<SegmentedControl label="Filter" options={OPTIONS} value="all" onChange={vi.fn()} />);

    const group = screen.getByRole('group', { name: 'Filter' });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Needs attention' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('reports the option the user picks', async () => {
    const onChange = vi.fn();
    render(<SegmentedControl label="Filter" options={OPTIONS} value="all" onChange={onChange} />);

    await userEvent.click(screen.getByRole('button', { name: 'Needs attention' }));

    expect(onChange).toHaveBeenCalledWith('attention');
  });
});

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { CitationChip } from '@/components/CitationChip';

describe('CitationChip', () => {
  it('opens the evidence it names when pressed', async () => {
    const onClick = vi.fn();
    render(
      <CitationChip aria-label="Evidence: brief.md, paragraph 2" onClick={onClick}>
        brief.md ¶2
      </CitationChip>,
    );

    const chip = screen.getByRole('button', { name: 'Evidence: brief.md, paragraph 2' });
    await userEvent.click(chip);

    expect(chip).toHaveTextContent('brief.md ¶2');
    expect(onClick).toHaveBeenCalledOnce();
  });
});

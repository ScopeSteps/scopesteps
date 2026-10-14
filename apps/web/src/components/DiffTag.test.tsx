import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DiffTag } from '@/components/DiffTag';

describe('DiffTag', () => {
  it('names each kind of change in words, with its sign hidden from screen readers', () => {
    render(
      <>
        <DiffTag kind="added" />
        <DiffTag kind="changed" />
        <DiffTag kind="removed" />
      </>,
    );

    for (const [label, sign] of [
      ['Added', '+'],
      ['Changed', '~'],
      ['Removed', '−'],
    ] as const) {
      const tag = screen.getByText(label);
      expect(tag).toBeVisible();
      expect(tag).toHaveTextContent(`${sign}${label}`);
      expect(screen.getByText(sign)).toHaveAttribute('aria-hidden', 'true');
    }
  });
});

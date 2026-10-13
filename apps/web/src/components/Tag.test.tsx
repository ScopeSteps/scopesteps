import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Tag } from '@/components/Tag';

describe('Tag', () => {
  it('shows its text in every tone, so the status never depends on colour alone', () => {
    render(
      <>
        <Tag>Neutral</Tag>
        <Tag tone="accent">Accent</Tag>
        <Tag tone="warn">Needs a decision</Tag>
        <Tag tone="bad">Blocked</Tag>
        <Tag tone="ok">Passed</Tag>
      </>,
    );

    for (const text of ['Neutral', 'Accent', 'Needs a decision', 'Blocked', 'Passed']) {
      expect(screen.getByText(text)).toBeVisible();
    }
  });
});

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Card } from '@/components/Card';

describe('Card', () => {
  it('groups its content and passes naming attributes through', () => {
    render(
      <Card role="group" aria-label="Question" tone="decide">
        <p>How late may a user cancel?</p>
      </Card>,
    );

    expect(screen.getByRole('group', { name: 'Question' })).toHaveTextContent(
      'How late may a user cancel?',
    );
  });
});

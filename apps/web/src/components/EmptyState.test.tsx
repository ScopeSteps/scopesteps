import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Button } from '@/components/Button';
import { EmptyState } from '@/components/EmptyState';

describe('EmptyState', () => {
  it('says what will appear and offers how to make it appear', () => {
    render(
      <EmptyState title="No sources yet" action={<Button variant="primary">Add source</Button>}>
        <p>Sources appear here after you upload them.</p>
      </EmptyState>,
    );

    expect(screen.getByRole('heading', { name: 'No sources yet' })).toBeInTheDocument();
    expect(screen.getByText('Sources appear here after you upload them.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Add source' })).toBeInTheDocument();
  });
});

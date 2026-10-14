import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';

describe('Banner', () => {
  it('announces a failure and offers the action that goes with it', () => {
    render(
      <Banner tone="bad" role="alert" action={<Button size="sm">Try again</Button>}>
        Could not load the sources.
      </Banner>,
    );

    expect(screen.getByRole('alert')).toHaveTextContent('Could not load the sources.');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('is plain text unless a role is asked for', () => {
    render(<Banner>Sources are read-only once a run has cited them.</Banner>);

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByText('Sources are read-only once a run has cited them.')).toBeVisible();
  });
});

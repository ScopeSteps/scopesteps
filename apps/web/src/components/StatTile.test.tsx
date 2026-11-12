import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';

import { Meter } from './Meter';
import { StatTile } from './StatTile';

function renderTile() {
  const router = createMemoryRouter([
    {
      path: '/',
      element: (
        <main>
          <StatTile label="Stories" value={12} detail="3 epics" to="/backlog">
            <Meter label="Covered" value={9} max={10} valueText="9 of 10" />
          </StatTile>
        </main>
      ),
    },
  ]);
  render(<RouterProvider router={router} />);
}

describe('StatTile', () => {
  it('is one link named by its label, figure, detail and meter', async () => {
    renderTile();

    expect(screen.getByRole('link', { name: 'Stories 12 3 epics 9 of 10' })).toHaveAttribute(
      'href',
      '/backlog',
    );
    await expectNoAccessibilityViolations();
  });
});

describe('Meter', () => {
  it('gives its value as text, never only as the fill', () => {
    renderTile();

    const meter = screen.getByRole('meter', { name: 'Covered' });
    expect(meter).toHaveAttribute('aria-valuenow', '9');
    expect(meter).toHaveAttribute('aria-valuemax', '10');
    expect(meter).toHaveAttribute('aria-valuetext', '9 of 10');
  });
});

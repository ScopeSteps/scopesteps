import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';

import { ButtonLink } from './ButtonLink';

describe('ButtonLink', () => {
  it('is a link to its destination that looks like a button', async () => {
    render(
      <MemoryRouter>
        <main>
          <ButtonLink to="/projects/1/backlog" variant="primary" size="sm">
            Open backlog
          </ButtonLink>
        </main>
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: 'Open backlog' })).toHaveAttribute(
      'href',
      '/projects/1/backlog',
    );
    await expectNoAccessibilityViolations();
  });
});

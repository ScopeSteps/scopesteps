import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { IMPACT } from '@/test/changeFixtures';

import { ImpactPanel } from './ImpactPanel';

describe('ImpactPanel', () => {
  it('shows the server’s figures as a summary, a chart and text', async () => {
    render(<ImpactPanel impact={IMPACT} name="CR-3" />);

    const panel = within(screen.getByRole('region', { name: 'Impact of CR-3 on scope' }));
    expect(
      panel.getByText('Adds 1 story, changes 1, removes 1. Raises 1 scope decision.'),
    ).toBeVisible();
    const chart = panel.getByRole('img', { name: 'Scope before and after CR-3' });
    expect(chart).toHaveAccessibleDescription(
      'Epics: 1 before, 1 after: 1 unchanged, 0 changed, 0 removed, 0 added. ' +
        'Stories: 3 before, 3 after: 1 unchanged, 1 changed, 1 removed, 1 added.',
    );
    expect(within(chart).getByTitle('1 removed')).toBeInTheDocument();
    expect(within(chart).getByTitle('1 added')).toBeInTheDocument();
    expect(within(chart).queryByText('Acceptance criteria')).toBeNull();
    expect(panel.getByRole('list', { name: 'Chart legend' })).toHaveTextContent(
      'UnchangedChangedRemovedAdded',
    );
    await expectNoAccessibilityViolations();
  });

  it('draws no chart when the change touches no work', () => {
    const untouched = {
      ...IMPACT,
      stories: { before: 3, after: 3, added: 0, changed: 0, removed: 0, unchanged: 3 },
      scope_decisions: 0,
    };

    render(<ImpactPanel impact={untouched} name="CR-3" />);

    expect(screen.getByText('Changes no stories.')).toBeVisible();
    expect(screen.queryByRole('img')).toBeNull();
  });
});

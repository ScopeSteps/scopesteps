import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { REVIEWER_ID, STORY_ID } from '@/test/fixtures';

import { PersonalDataNotice } from './PersonalDataNotice';
import type { PersonalDataFlag } from './types';

const FLAG: PersonalDataFlag = {
  id: 'f1a2b3c4d5e6f7a8b9c0',
  item_id: STORY_ID,
  criterion_id: null,
  task_id: null,
  kind: 'email',
  place: 'description',
  value: 'desk@rooms.example',
  reason: 'An email address in the description',
  kept_by: null,
  kept_at: null,
};

describe('Personal data on an item', () => {
  it('warns in plain words with what was found and what to do', () => {
    render(<PersonalDataNotice flags={[FLAG]} itemTitle="Cancel a booking" />);

    const list = within(screen.getByRole('list', { name: 'Personal data in Cancel a booking' }));
    expect(list.getByRole('listitem')).toHaveTextContent(
      'Personal data: An email address in the description (desk@rooms.example). Edit it out',
    );
  });

  it('shows a value an approver kept on purpose as settled', () => {
    const kept = { ...FLAG, kept_by: REVIEWER_ID, kept_at: '2026-11-13T10:00:00Z' };

    render(<PersonalDataNotice flags={[kept]} itemTitle="Cancel a booking" />);

    expect(screen.getByRole('listitem')).toHaveTextContent(
      'Kept on purpose: An email address in the description (desk@rooms.example).',
    );
    expect(screen.queryByText(/Edit it out/)).not.toBeInTheDocument();
  });

  it('shows nothing for an item without personal data', () => {
    const { container } = render(<PersonalDataNotice flags={[]} itemTitle="Cancel a booking" />);

    expect(container).toBeEmptyDOMElement();
  });
});

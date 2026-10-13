import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Avatar } from '@/components/Avatar';

describe('Avatar', () => {
  it.each([
    ['Local Reviewer', 'LR'],
    ['  dana  ', 'D'],
    ['Alex Morgan Lee', 'AM'],
  ])('shows the initials of %j as %s', (name, initials) => {
    const { container } = render(<Avatar name={name} />);

    expect(container).toHaveTextContent(initials);
  });
});

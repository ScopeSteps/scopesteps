import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Badge } from '@/components/Badge';

describe('Badge', () => {
  it('shows the count and reads out what it counts', () => {
    render(<Badge count={3} label="3 need attention" />);

    expect(screen.getByText('3')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByText('3 need attention')).toBeInTheDocument();
  });

  it('renders nothing when there is nothing to count', () => {
    const { container } = render(<Badge count={0} label="0 need attention" />);

    expect(container).toBeEmptyDOMElement();
  });
});

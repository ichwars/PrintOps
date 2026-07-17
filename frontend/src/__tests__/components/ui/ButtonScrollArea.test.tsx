import { render, screen } from '@testing-library/react';
import { RefreshCw } from 'lucide-react';
import { describe, expect, it } from 'vitest';

import { Button, IconButton, ScrollArea } from '../../../components/ui';

describe('button and scroll-area controls', () => {
  it('requires an accessible icon label and exposes pressed state', () => {
    render(<IconButton label="Refresh" icon={RefreshCw} pressed onClick={() => {}} />);

    expect(screen.getByRole('button', { name: 'Refresh' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('selects native scrolling classes by variant', () => {
    render(
      <ScrollArea data-testid="area" direction="both" scrollbar="thin" stableGutter />,
    );

    expect(screen.getByTestId('area')).toHaveClass(
      'overflow-auto',
      'scrollbar-thin',
      'scrollbar-gutter-stable',
    );
  });

  it('disables and marks a loading button while preserving its label', () => {
    render(<Button loading>Save</Button>);

    expect(screen.getByRole('button', { name: /Save/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Save/ })).toHaveAttribute('aria-busy', 'true');
  });
});

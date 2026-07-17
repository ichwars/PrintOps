import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRef } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { FloatingLayer } from '../../../components/ui';

describe('FloatingLayer', () => {
  it('portals a floating layer and dismisses outside pointer events', async () => {
    const onDismiss = vi.fn();

    function Harness() {
      const ref = useRef<HTMLButtonElement>(null);
      return (
        <>
          <button ref={ref}>Anchor</button>
          <FloatingLayer open anchorRef={ref} onDismiss={onDismiss}>
            Menu
          </FloatingLayer>
        </>
      );
    }

    render(<Harness />);

    expect(screen.getByText('Menu')).toBe(document.body.lastElementChild);
    await userEvent.setup().click(document.body);
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});

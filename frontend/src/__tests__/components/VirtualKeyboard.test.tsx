import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

import { VirtualKeyboard } from '../../components/VirtualKeyboard';

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('VirtualKeyboard (#2616)', () => {
  it('renders the keyboard when a text input is focused', () => {
    render(
      <div>
        <input type="text" placeholder="Search spools..." />
        <VirtualKeyboard />
      </div>,
    );

    fireEvent.focusIn(screen.getByPlaceholderText('Search spools...'));

    expect(screen.getByText('q')).toBeInTheDocument();
  });
});

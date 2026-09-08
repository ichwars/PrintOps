import { describe, expect, it, vi } from 'vitest';
import { fireEvent } from '@testing-library/react';
import { listenForOutsideScroll } from '../../utils/outsideScroll';

describe('outside scroll dismissal', () => {
  it('ignores delayed notifications but detects subsequent document or ancestor movement', () => {
    const ancestor = document.createElement('div');
    const anchor = document.createElement('button');
    const menu = document.createElement('div');
    ancestor.append(anchor);
    document.body.append(ancestor, menu);
    const dismiss = vi.fn();
    const initialY = window.scrollY;
    const cleanup = listenForOutsideScroll(menu, anchor, dismiss);
    try {
      fireEvent.scroll(document);
      fireEvent.scroll(ancestor);
      expect(dismiss).not.toHaveBeenCalled();
      ancestor.scrollLeft = 12;
      fireEvent.scroll(ancestor);
      expect(dismiss).toHaveBeenCalledTimes(1);
      Object.defineProperty(window, 'scrollY', { configurable: true, value: initialY + 20 });
      fireEvent.scroll(document);
      expect(dismiss).toHaveBeenCalledTimes(2);
      fireEvent.scroll(menu);
      expect(dismiss).toHaveBeenCalledTimes(2);
      cleanup();
      fireEvent.scroll(document);
      expect(dismiss).toHaveBeenCalledTimes(2);
    } finally {
      cleanup();
      Object.defineProperty(window, 'scrollY', { configurable: true, value: initialY });
      ancestor.remove();
      menu.remove();
    }
  });
});

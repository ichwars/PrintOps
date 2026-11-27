import { act, fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

import { WarehouseTable, WarehouseTableScroll } from '../../components/warehouse/WarehouseLayout';

it('shows the scrollbar only for overflow and keeps both scroll controls in sync', () => {
  const OriginalResizeObserver = ResizeObserver;
  const observe = vi.fn();
  const disconnect = vi.fn();
  let measure: () => void = () => {};
  class TestResizeObserver {
    observe = observe;
    disconnect = disconnect;
    constructor(callback: () => void) {
      measure = callback;
    }
  }
  vi.stubGlobal('ResizeObserver', TestResizeObserver);

  try {
    const { unmount } = render(
      <WarehouseTable>
        <WarehouseTableScroll label="Stock">
          <table><tbody><tr><td>Item</td></tr></tbody></table>
        </WarehouseTableScroll>
      </WarehouseTable>,
    );
    const viewport = screen.getByRole('region', { name: 'Stock' });
    let width = 800;
    Object.defineProperties(viewport, {
      clientWidth: { get: () => width },
      scrollWidth: { get: () => 800 },
    });
    act(measure);
    expect(screen.queryByRole('slider')).toBeNull();
    expect(observe).toHaveBeenCalledWith(viewport);
    expect(observe).toHaveBeenCalledWith(screen.getByRole('table'));

    width = 500;
    act(measure);
    const scrollbar = screen.getByRole<HTMLInputElement>('slider', { name: 'Scroll Stock table horizontally' });
    expect(scrollbar).toHaveAttribute('aria-controls', viewport.id);
    expect(scrollbar.max).toBe('300');
    fireEvent.change(scrollbar, { target: { value: '150' } });
    expect(viewport.scrollLeft).toBe(150);
    fireEvent.keyDown(scrollbar, { key: 'ArrowRight' });
    expect(viewport.scrollLeft).toBe(198);

    viewport.scrollLeft = 70;
    fireEvent.scroll(viewport);
    expect(scrollbar.value).toBe('70');

    width = 800;
    act(measure);
    expect(screen.queryByRole('slider')).toBeNull();
    unmount();
    expect(disconnect).toHaveBeenCalledOnce();
  } finally {
    vi.stubGlobal('ResizeObserver', OriginalResizeObserver);
  }
});

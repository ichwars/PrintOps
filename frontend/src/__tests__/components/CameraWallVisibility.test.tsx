import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from '@testing-library/react';
import { render } from '../utils';
import { CameraWall, type CameraWallStatus } from '../../components/CameraWall';

// The wall must not keep pulling frames that nobody can see: hidden tabs
// pause every tile, and a tile only leaves the visible set below the 10%
// exit threshold (slow-scrolling across the 40% entry line used to flip a
// tile between live and paused — tearing the stream down and rebuilding it).

interface FakeEntry {
  target: HTMLElement;
  intersectionRatio: number;
}

class ControllableIntersectionObserver {
  static callback: ((entries: FakeEntry[]) => void) | null = null;
  static elements: HTMLElement[] = [];
  constructor(callback: (entries: FakeEntry[]) => void) {
    ControllableIntersectionObserver.callback = callback;
  }
  observe = (el: Element) => {
    ControllableIntersectionObserver.elements.push(el as HTMLElement);
    ControllableIntersectionObserver.callback?.([{ target: el as HTMLElement, intersectionRatio: 1 }]);
  };
  unobserve = vi.fn();
  disconnect = vi.fn();
  takeRecords = () => [];
  root = null;
  rootMargin = '';
  thresholds = [0, 0.1, 0.4];
}

function fireVisibility(ratio: number) {
  const callback = ControllableIntersectionObserver.callback;
  const elements = ControllableIntersectionObserver.elements;
  act(() => {
    callback?.(elements.map((target) => ({ target, intersectionRatio: ratio })));
  });
}

function setPageVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });
  act(() => {
    document.dispatchEvent(new Event('visibilitychange'));
  });
}

describe('CameraWall visibility economics', () => {
  beforeEach(() => {
    vi.stubGlobal('IntersectionObserver', ControllableIntersectionObserver);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function renderWall() {
    const statuses = new Map<number, CameraWallStatus | undefined>([[1, { connected: true }]]);
    return render(
      <CameraWall
        printers={[{ id: 1, name: 'X1C-Lab' }]}
        maxLive={2}
        snapshotIntervalSec={5}
        statusMode="off"
        onChangeMaxLive={() => {}}
        onChangeSnapshotIntervalSec={() => {}}
        onChangeStatusMode={() => {}}
        statuses={statuses}
      />,
    );
  }

  it('keeps a partially visible tile live (hysteresis) and pauses it below the exit threshold', async () => {
    const view = renderWall();
    await act(async () => { await Promise.resolve(); });
    expect(view.container.querySelector('img')).toHaveAttribute('src', expect.stringContaining('/camera/stream'));

    // Still above the 10% exit threshold: no teardown.
    fireVisibility(0.2);
    expect(view.container.querySelector('img')).toHaveAttribute('src', expect.stringContaining('/camera/stream'));

    // Below 10%: paused — the img and its stream request are gone.
    fireVisibility(0.05);
    expect(view.container.querySelector('img')).toBeNull();

    // Fully visible again: back to live.
    fireVisibility(1);
    await act(async () => { await Promise.resolve(); });
    expect(view.container.querySelector('img')).toHaveAttribute('src', expect.stringContaining('/camera/stream'));
  });

  it('pauses every tile while the tab is hidden and resumes when it returns', async () => {
    const view = renderWall();
    await act(async () => { await Promise.resolve(); });
    expect(view.container.querySelector('img')).toHaveAttribute('src', expect.stringContaining('/camera/stream'));

    setPageVisibility('hidden');
    expect(view.container.querySelector('img')).toBeNull();

    setPageVisibility('visible');
    await act(async () => { await Promise.resolve(); });
    expect(view.container.querySelector('img')).toHaveAttribute('src', expect.stringContaining('/camera/stream'));
  });
});

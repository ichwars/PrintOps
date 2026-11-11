import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, screen } from '@testing-library/react';
import { render } from '../utils';
import { CameraTile } from '../../components/CameraTile';

// The shared render() util mounts AuthProvider, which fires an async
// /auth/me probe on mount. Each test absorbs that settle with a single
// `await act(async () => {})` after render so the AuthProvider state
// update doesn't bleed into the assertion phase as an act() warning.
async function flushMicrotasks() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe('CameraTile', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 200 }));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('assigns the stream to an attached image and releases it on unmount', async () => {
    const setSrc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src')!.set!;
    const writes: boolean[] = [];
    vi.spyOn(HTMLImageElement.prototype, 'src', 'set').mockImplementation(function (this: HTMLImageElement, src) {
      if (src.includes('/camera/stream')) writes.push(this.isConnected);
      setSrc.call(this, src);
    });
    const view = render(
      <CameraTile
        printerId={42}
        printerName="X1C-Lab"
        mode="live"
        snapshotIntervalMs={5000}
        connected
      />,
    );
    await flushMicrotasks();
    const img = screen.getByAltText('X1C-Lab') as HTMLImageElement;
    expect(img.src).toContain('/api/v1/printers/42/camera/stream');
    expect(img.src).toContain('fps=8');
    expect(writes.length).toBeGreaterThan(0);
    expect(writes.every(Boolean)).toBe(true);
    view.unmount();
    expect(img).not.toHaveAttribute('src');
  });

  it('renders the snapshot URL and refreshes on the interval', async () => {
    render(
      <CameraTile
        printerId={7}
        printerName="P1S-Garage"
        mode="snapshot"
        snapshotIntervalMs={1000}
        connected
      />,
    );
    await flushMicrotasks();
    const initial = (screen.getByAltText('P1S-Garage') as HTMLImageElement).src;
    expect(initial).toContain('/api/v1/printers/7/camera/snapshot');

    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    const refreshed = (screen.getByAltText('P1S-Garage') as HTMLImageElement).src;
    expect(refreshed).toContain('/api/v1/printers/7/camera/snapshot');
    expect(refreshed).not.toBe(initial);
  });

  it('renews a stalled live feed and releases its image while retrying', async () => {
    render(<CameraTile printerId={42} printerName="X1C-Lab" mode="live" snapshotIntervalMs={5000}
      cameraToken="kiosk-fixture" connected />);
    await flushMicrotasks();
    const first = screen.getByAltText('X1C-Lab');
    await act(async () => { vi.advanceTimersByTime(60000); });
    const renewed = screen.getByAltText('X1C-Lab');
    expect(first).not.toHaveAttribute('src');
    expect(renewed).toHaveAttribute('src', expect.stringContaining('token=kiosk-fixture'));
    fireEvent.error(renewed);
    expect(renewed).not.toHaveAttribute('src');
    await act(async () => { vi.advanceTimersByTime(6000); });
    const reopened = screen.getByAltText('X1C-Lab');
    expect(reopened).not.toBe(renewed);
    expect(reopened).toHaveAttribute('src', expect.stringContaining('token=kiosk-fixture'));
  });

  it('shows an offline placeholder when not connected', async () => {
    render(
      <CameraTile
        printerId={1}
        printerName="A1-Offline"
        mode="live"
        snapshotIntervalMs={5000}
        connected={false}
      />,
    );
    await flushMicrotasks();
    expect(screen.queryByAltText('A1-Offline')).toBeNull();
  });

  it('retries a snapshot once at the next refresh', async () => {
    render(<CameraTile printerId={7} printerName="P1S-Garage" mode="snapshot" snapshotIntervalMs={1000} connected />);
    await flushMicrotasks();
    const first = screen.getByAltText('P1S-Garage');
    fireEvent.error(first);
    expect(screen.queryByText('No signal')).not.toBeInTheDocument();
    await act(async () => { vi.advanceTimersByTime(1000); });
    const retry = screen.getByAltText('P1S-Garage');
    expect(retry).not.toBe(first);
    fireEvent.error(retry);
    expect(screen.getByText('No signal')).toBeInTheDocument();
  });

  it('shows the paused placeholder in paused mode', async () => {
    render(
      <CameraTile
        printerId={9}
        printerName="H2D-Booth"
        mode="paused"
        snapshotIntervalMs={5000}
        connected
      />,
    );
    await flushMicrotasks();
    expect(screen.queryByAltText('H2D-Booth')).toBeNull();
  });

  it('POSTs /camera/stop when leaving live mode', async () => {
    const fetchMock = vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(null, { status: 200 }),
    );
    const { rerender } = render(
      <CameraTile
        printerId={11}
        printerName="X1C-Stop"
        mode="live"
        snapshotIntervalMs={5000}
        connected
      />,
    );
    await flushMicrotasks();
    fetchMock.mockClear();

    await act(async () => {
      rerender(
        <CameraTile
          printerId={11}
          printerName="X1C-Stop"
          mode="snapshot"
          snapshotIntervalMs={5000}
          connected
        />,
      );
    });

    const stopCalls = fetchMock.mock.calls.filter(([url]) =>
      String(url).includes('/api/v1/printers/11/camera/stop'),
    );
    expect(stopCalls.length).toBeGreaterThan(0);
  });
});

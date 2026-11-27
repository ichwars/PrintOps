import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useCameraStream } from '../../hooks/useCameraStream';

// A dropped MSE socket is usually transient (Wi-Fi handover, standby
// resume). The hook must retry with backoff before reporting 'error' — the
// viewer treats 'error' as "fall back to MJPEG permanently", and a single
// network blip must not cost the session the efficient H.264 path.

class FakeMediaSource extends EventTarget {
  readyState = 'closed';
  static isTypeSupported() { return true; }
}

class RecordingSocket {
  static instances: RecordingSocket[] = [];
  onopen: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  send = vi.fn();
  close = vi.fn();
  constructor() {
    RecordingSocket.instances.push(this);
  }
}

function Probe({ onError, onStatus }: { onError: () => void; onStatus: (s: string) => void }) {
  const { videoRef, status } = useCameraStream({ printerId: 1, enabled: true, onError });
  onStatus(status);
  return <video ref={videoRef} />;
}

async function renderProbe(onError: () => void, onStatus: (s: string) => void) {
  const view = render(<Probe onError={onError} onStatus={onStatus} />);
  await act(async () => { await Promise.resolve(); });
  return view;
}

describe('useCameraStream reconnect', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    RecordingSocket.instances = [];
    vi.stubGlobal('MediaSource', FakeMediaSource);
    vi.stubGlobal('WebSocket', RecordingSocket);
    vi.stubGlobal('URL', class extends URL {
      static createObjectURL() { return 'blob:camera-test'; }
      static revokeObjectURL() {}
    });
    // jsdom has no real media pipeline; the hook calls load() on teardown.
    vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('retries a dropped socket with backoff before giving up', async () => {
    const onError = vi.fn();
    const statuses: string[] = [];
    await renderProbe(onError, (s) => statuses.push(s));
    expect(RecordingSocket.instances.length).toBe(1);

    // 1st failure → retry after 2 s
    act(() => { RecordingSocket.instances[0].onclose?.(new CloseEvent('close')); });
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(RecordingSocket.instances.length).toBe(2);

    // 2nd failure → retry after 4 s
    act(() => { RecordingSocket.instances[1].onerror?.(new Event('error')); });
    await act(() => vi.advanceTimersByTimeAsync(4000));
    expect(RecordingSocket.instances.length).toBe(3);

    // 3rd failure → retry after 8 s
    act(() => { RecordingSocket.instances[2].onclose?.(new CloseEvent('close')); });
    await act(() => vi.advanceTimersByTimeAsync(8000));
    expect(RecordingSocket.instances.length).toBe(4);

    // 4th failure → give up: report error, no further sockets
    act(() => { RecordingSocket.instances[3].onclose?.(new CloseEvent('close')); });
    expect(onError).toHaveBeenCalledTimes(1);
    expect(statuses.at(-1)).toBe('error');
    await act(() => vi.advanceTimersByTimeAsync(60000));
    expect(RecordingSocket.instances.length).toBe(4);
  });

  it('counts one dropped connection once even when error and close both fire', async () => {
    const onError = vi.fn();
    await renderProbe(onError, () => {});
    expect(RecordingSocket.instances.length).toBe(1);
    act(() => {
      RecordingSocket.instances[0].onerror?.(new Event('error'));
      RecordingSocket.instances[0].onclose?.(new CloseEvent('close'));
    });
    await act(() => vi.advanceTimersByTimeAsync(2000));
    // A single reconnect was scheduled — not two parallel ones.
    expect(RecordingSocket.instances.length).toBe(2);
  });

  it('does not retry after the viewer unmounts mid-backoff', async () => {
    const onError = vi.fn();
    const view = await renderProbe(onError, () => {});
    expect(RecordingSocket.instances.length).toBe(1);
    act(() => { RecordingSocket.instances[0].onclose?.(new CloseEvent('close')); });
    view.unmount();
    await act(() => vi.advanceTimersByTimeAsync(60000));
    expect(RecordingSocket.instances.length).toBe(1);
    expect(onError).not.toHaveBeenCalled();
  });
});

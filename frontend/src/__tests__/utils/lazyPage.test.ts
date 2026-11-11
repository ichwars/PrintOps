import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

describe('lazy page recovery', () => {
  const fetch = vi.fn();
  const reload = vi.fn();

  beforeEach(() => {
    vi.resetModules();
    vi.useFakeTimers();
    vi.stubGlobal('fetch', fetch.mockReset());
    vi.stubGlobal('window', { location: { reload: reload.mockReset() } });
    sessionStorage.clear();
  });

  afterEach(() => {
    sessionStorage.clear();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('recognizes missing chunks across browsers and leaves application errors to the error boundary', async () => {
    const { isChunkLoadError } = await import('../../utils/lazyPage');
    expect(isChunkLoadError(new TypeError('Failed to fetch dynamically imported module: /assets/queue.js'))).toBe(true);
    expect(isChunkLoadError(new TypeError('Importing a module script failed.'))).toBe(true);
    expect(isChunkLoadError(new Error('Unable to preload CSS for /assets/index.css'))).toBe(true);
    expect(isChunkLoadError(new Error('Unexpected response from the archive API'))).toBe(false);
  });

  it('waits through a restart and shares one reload across simultaneous failures', async () => {
    fetch.mockRejectedValueOnce(new TypeError('Network error'))
      .mockResolvedValueOnce({ status: 502 })
      .mockResolvedValueOnce({ status: 200 });
    const { recoverFromMissingChunk } = await import('../../utils/lazyPage');
    const first = recoverFromMissingChunk();
    expect(recoverFromMissingChunk()).toBe(first);
    expect(reload).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(3_000);
    expect(reload).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(3_000);
    expect(await first).toBe(true);
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(fetch).toHaveBeenCalledWith('/health', expect.objectContaining({ cache: 'no-store', redirect: 'manual' }));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('allows the error screen after a recent reload and can retry after the cooldown', async () => {
    fetch.mockResolvedValue({ status: 200 });
    sessionStorage.setItem('printops:chunk-reload-at', String(Date.now()));
    const { recoverFromMissingChunk } = await import('../../utils/lazyPage');
    expect(await recoverFromMissingChunk()).toBe(false);
    expect(reload).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(await recoverFromMissingChunk()).toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
  });
});

import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useCameraFeedRecovery } from '../../hooks/useCameraFeedRecovery';

afterEach(() => vi.useRealTimers());
it('renews a silent connection at most three times without a successful load', async () => {
  vi.useFakeTimers();
  const { result } = renderHook(() => useCameraFeedRecovery(true, '1:bblt_fixture:15'));
  for (const key of [1, 2, 3]) {
    await act(() => vi.advanceTimersByTimeAsync(60000));
    expect(result.current.imageKey).toBe(key);
  }
  act(() => result.current.onLoad());
  await act(() => vi.advanceTimersByTimeAsync(60000));
  expect(result.current.imageKey).toBe(4);
  await act(() => vi.advanceTimersByTimeAsync(600000));
  expect(result.current.imageKey).toBe(6);
  expect(result.current.failed).toBe(true);
});
it('coalesces errors and cancels pending recovery when camera is hidden or unmounted', async () => {
  vi.useFakeTimers();
  const { result, rerender, unmount } = renderHook(({ enabled }) => useCameraFeedRecovery(enabled, '1'), { initialProps: { enabled: true } });
  act(() => { result.current.onError(); result.current.onError(); });
  await act(() => vi.advanceTimersByTimeAsync(3000));
  expect(result.current.imageKey).toBe(1);
  rerender({ enabled: false });
  await act(() => vi.advanceTimersByTimeAsync(120000));
  expect(result.current.imageKey).toBe(1);
  rerender({ enabled: true });
  unmount();
  expect(vi.getTimerCount()).toBe(0);
});

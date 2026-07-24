import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useAutosaveDraft } from '../../hooks/useAutosaveDraft';

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void; reject: (error: Error) => void };

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe('useAutosaveDraft', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('waits for the complete 500 ms debounce before saving', async () => {
    vi.useFakeTimers();
    const adapter = vi.fn(async (draft: { value: number }) => draft.value);
    const onConfirmed = vi.fn();

    const { result } = renderHook(() =>
      useAutosaveDraft({
        draft: { value: 1 },
        enabled: true,
        fingerprint: draft => String(draft.value),
        adapter,
        onConfirmed,
      }),
    );

    expect(result.current.status).toBe('pending');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(499);
    });
    expect(adapter).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(adapter).toHaveBeenCalledOnce();
    expect(result.current.status).toBe('saved');
    expect(onConfirmed).toHaveBeenCalledWith(1, { value: 1 });
  });

  it('aborts an older request and ignores its stale completion when the draft changes', async () => {
    vi.useFakeTimers();
    const first = deferred<number>();
    const second = deferred<number>();
    const signals: AbortSignal[] = [];
    const adapter = vi.fn((draft: { value: number }, signal: AbortSignal) => {
      signals.push(signal);
      return draft.value === 1 ? first.promise : second.promise;
    });
    const onConfirmed = vi.fn();

    const { result, rerender } = renderHook(
      ({ value }) =>
        useAutosaveDraft({
          draft: { value },
          enabled: true,
          fingerprint: draft => String(draft.value),
          adapter,
          onConfirmed,
        }),
      { initialProps: { value: 1 } },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(result.current.status).toBe('saving');

    rerender({ value: 2 });
    expect(signals[0].aborted).toBe(true);
    expect(result.current.status).toBe('pending');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
      first.resolve(1);
      await Promise.resolve();
    });
    expect(onConfirmed).not.toHaveBeenCalled();

    await act(async () => {
      second.resolve(2);
      await Promise.resolve();
    });
    expect(result.current.status).toBe('saved');
    expect(onConfirmed).toHaveBeenCalledOnce();
    expect(onConfirmed).toHaveBeenCalledWith(2, { value: 2 });
  });


  it('keeps a failed draft retryable without requiring another edit', async () => {
    vi.useFakeTimers();
    const adapter = vi
      .fn<(draft: { value: number }, signal: AbortSignal) => Promise<number>>()
      .mockRejectedValueOnce(new Error('network unavailable'))
      .mockResolvedValueOnce(7);

    const { result } = renderHook(() =>
      useAutosaveDraft({
        draft: { value: 7 },
        enabled: true,
        fingerprint: draft => String(draft.value),
        adapter,
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(result.current.status).toBe('error');
    expect(result.current.error?.message).toBe('network unavailable');

    act(() => result.current.retry());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(adapter).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe('saved');
    expect(result.current.error).toBeNull();
  });


  it('does not save an already confirmed fingerprint again after re-enabling', async () => {
    vi.useFakeTimers();
    const adapter = vi.fn(async (draft: { value: number }) => draft.value);

    const { result, rerender } = renderHook(
      ({ enabled }) =>
        useAutosaveDraft({
          draft: { value: 4 },
          enabled,
          fingerprint: draft => String(draft.value),
          adapter,
        }),
      { initialProps: { enabled: true } },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(result.current.status).toBe('saved');

    rerender({ enabled: false });
    rerender({ enabled: true });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(adapter).toHaveBeenCalledOnce();
    expect(result.current.status).toBe('saved');
  });


  it('keeps only one timer and saves the latest debounced draft', async () => {
    vi.useFakeTimers();
    const adapter = vi.fn(async (draft: { value: number }) => draft.value);
    const { rerender } = renderHook(
      ({ value }) =>
        useAutosaveDraft({
          draft: { value },
          enabled: true,
          fingerprint: draft => String(draft.value),
          adapter,
        }),
      { initialProps: { value: 1 } },
    );

    rerender({ value: 2 });
    rerender({ value: 3 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(adapter).toHaveBeenCalledOnce();
    expect(adapter.mock.calls[0][0]).toEqual({ value: 3 });
  });

  it('clears its timer and aborts its active request on unmount', async () => {
    vi.useFakeTimers();
    const pending = deferred<number>();
    const adapter = vi.fn((_draft: { value: number }, _signal: AbortSignal) => pending.promise);
    const onConfirmed = vi.fn();
    const first = renderHook(() =>
      useAutosaveDraft({
        draft: { value: 1 },
        enabled: true,
        fingerprint: draft => String(draft.value),
        adapter,
        onConfirmed,
      }),
    );
    first.unmount();
    await vi.advanceTimersByTimeAsync(500);
    expect(adapter).not.toHaveBeenCalled();

    const second = renderHook(() =>
      useAutosaveDraft({
        draft: { value: 2 },
        enabled: true,
        fingerprint: draft => String(draft.value),
        adapter,
        onConfirmed,
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    const signal = adapter.mock.calls[0][1];
    second.unmount();
    expect(signal.aborted).toBe(true);
    pending.resolve(2);
    await Promise.resolve();
    expect(onConfirmed).not.toHaveBeenCalled();
  });

});

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { usePrinterCardTextScale } from '../../hooks/usePrinterCardTextScale';

let auth: { authEnabled: boolean; authStatusVerified: boolean; loading: boolean; preferenceSubject: string | null; user: { id: number; sub?: string } | null };
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => auth }));
const prefix = 'printops:card-text-scale:v1:http%3A%2F%2Flocalhost%3A3000:';

describe('printer card scale storage boundaries', () => {
  let storage: Map<string, string>;
  beforeEach(() => {
    auth = { authStatusVerified: true, authEnabled: true, loading: false, preferenceSubject: 'original', user: { id: 7, sub: 'original' } };
    storage = new Map();
    vi.mocked(localStorage.getItem).mockImplementation(key => storage.get(key) ?? null);
    vi.mocked(localStorage.setItem).mockImplementation((key, value) => { storage.set(key, value); });
    vi.mocked(localStorage.removeItem).mockImplementation(key => { storage.delete(key); });
  });
  afterEach(() => {
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.setItem).mockReset();
    vi.mocked(localStorage.removeItem).mockReset();
  });

  it('restores a returning account, but never a recreated account sharing its numeric ID', () => {
    const renders: number[] = [];
    const hook = renderHook(() => {
      const value = usePrinterCardTextScale();
      renders.push(value.scale);
      return value;
    });
    expect(hook.result.current.scale).toBe(100);
    act(() => hook.result.current.setScale(120));
    expect(storage.get(prefix + 'user:original')).toBe('120');
    auth = { ...auth, preferenceSubject: 'second', user: { id: 8, sub: 'second' } };
    hook.rerender();
    expect(hook.result.current.scale).toBe(100);
    act(() => hook.result.current.setScale(90));
    auth = { ...auth, preferenceSubject: null, user: null };
    hook.rerender();
    expect(hook.result.current.scale).toBe(100);
    expect(hook.result.current.ready).toBe(false);
    auth = { ...auth, preferenceSubject: 'replacement', user: { id: 7, sub: 'replacement' } };
    const before = renders.length;
    hook.rerender();
    expect(renders.slice(before)).not.toContain(120);
    expect(hook.result.current.scale).toBe(100);
    auth = { ...auth, preferenceSubject: 'original', user: { id: 7, sub: 'original' } };
    hook.rerender();
    expect(hook.result.current.scale).toBe(120);
    act(() => hook.result.current.setScale(100));
    expect(storage.has(prefix + 'user:original')).toBe(false);
    auth = { ...auth, preferenceSubject: 'second', user: { id: 8, sub: 'second' } };
    hook.rerender();
    expect(hook.result.current.scale).toBe(90);
  });

  it('does not persist under numeric-only, synthetic, signed-out or unresolved identities', () => {
    storage.set(prefix + 'appliance', '120');
    auth = { authStatusVerified: false, authEnabled: false, loading: true, preferenceSubject: null, user: null };
    const hook = renderHook(() => usePrinterCardTextScale());
    expect(hook.result.current.scale).toBe(100);
    act(() => hook.result.current.setScale(90));
    expect(storage.get(prefix + 'appliance')).toBe('120');
    auth = { ...auth, authStatusVerified: true, loading: false };
    hook.rerender();
    expect(hook.result.current.scale).toBe(120);
    for (const user of [{ id: 7 }, { id: 0 }, null]) {
      auth = { authStatusVerified: true, authEnabled: true, loading: false, preferenceSubject: null, user };
      hook.rerender();
      expect(hook.result.current.scale).toBe(100);
      expect(hook.result.current.ready).toBe(false);
      act(() => hook.result.current.setScale(90));
      expect(hook.result.current.scale).toBe(100);
    }
    expect(storage.size).toBe(1);
  });

  it.each(['NaN', '200', '0', '-90', '90.5', '120oops', '{}', 'null'])('ignores corrupt saved scale %s and rejects unsupported changes', value => {
    storage.set(prefix + 'user:original', value);
    const hook = renderHook(() => usePrinterCardTextScale());
    expect(hook.result.current.scale).toBe(100);
    act(() => hook.result.current.setScale(999));
    expect(hook.result.current.scale).toBe(100);
    act(() => hook.result.current.setScale(110));
    expect(hook.result.current.scale).toBe(110);
  });

  it('shares changes with mounted cards and responds to another tab or storage reset', () => {
    const toolbar = renderHook(() => usePrinterCardTextScale());
    const card = renderHook(() => usePrinterCardTextScale());
    act(() => toolbar.result.current.setScale(90));
    expect(card.result.current.scale).toBe(90);
    storage.set(prefix + 'user:original', '110');
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: prefix + 'user:original' })));
    expect(card.result.current.scale).toBe(110);
    storage.clear();
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: null })));
    expect(card.result.current.scale).toBe(100);
  });

  it('keeps blocked-storage choices usable across cards and scoped to the stable subject', () => {
    auth = { ...auth, preferenceSubject: 'blocked-original', user: { id: 7, sub: 'blocked-original' } };
    vi.mocked(localStorage.getItem).mockImplementation(() => { throw Error('blocked'); });
    vi.mocked(localStorage.setItem).mockImplementation(() => { throw Error('blocked'); });
    vi.mocked(localStorage.removeItem).mockImplementation(() => { throw Error('blocked'); });
    const toolbar = renderHook(() => usePrinterCardTextScale());
    const card = renderHook(() => usePrinterCardTextScale());
    act(() => toolbar.result.current.setScale(120));
    expect(card.result.current.scale).toBe(120);
    auth = { ...auth, preferenceSubject: 'blocked-replacement', user: { id: 7, sub: 'blocked-replacement' } };
    card.rerender();
    expect(card.result.current.scale).toBe(100);
    auth = { ...auth, preferenceSubject: 'blocked-original', user: { id: 7, sub: 'blocked-original' } };
    card.rerender();
    expect(card.result.current.scale).toBe(120);
    act(() => toolbar.result.current.setScale(100));
    expect(card.result.current.scale).toBe(100);
  });
});

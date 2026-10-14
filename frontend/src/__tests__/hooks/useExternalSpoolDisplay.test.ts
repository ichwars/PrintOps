import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useExternalSpoolDisplay } from '../../hooks/useExternalSpoolDisplay';

let auth: { authEnabled: boolean; authStatusVerified: boolean; loading: boolean; preferenceSubject: string | null; user: { id: number; sub?: string } | null };
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => auth }));
const prefix = 'printops:external-spool-hidden:v1:http%3A%2F%2Flocalhost%3A3000:';
const key = prefix + 'user:original:printer:serial-a';

describe('external spool display persistence boundaries', () => {
  let storage: Map<string, string>;
  beforeEach(() => {
    auth = { authEnabled: true, authStatusVerified: true, loading: false, preferenceSubject: 'original', user: { id: 7, sub: 'original' } };
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

  it('does not transfer a hidden preference to replacement hardware reusing the same database ID', () => {
    const hook = renderHook(({ printer }) => useExternalSpoolDisplay(printer.serial_number), {
      initialProps: { printer: { id: 1, serial_number: 'serial-a' } },
    });
    act(() => hook.result.current.setHidden(true));
    expect(storage.get(key)).toBe('true');
    hook.rerender({ printer: { id: 1, serial_number: 'serial-b' } });
    expect(hook.result.current.hidden).toBe(false);
    hook.rerender({ printer: { id: 22, serial_number: 'serial-a' } });
    expect(hook.result.current.hidden).toBe(true);
  });

  it('uses only the verified subject when stale business user data or a recreated same-ID account arrives', () => {
    const renders: boolean[] = [];
    const hook = renderHook(() => { const result = useExternalSpoolDisplay('serial-a'); renders.push(result.hidden); return result; });
    act(() => hook.result.current.setHidden(true));
    auth = { ...auth, preferenceSubject: 'replacement', user: { id: 7, sub: 'original' } };
    const before = renders.length;
    hook.rerender();
    expect(renders.slice(before)).not.toContain(true);
    act(() => hook.result.current.setHidden(true));
    expect(storage.get(prefix + 'user:replacement:printer:serial-a')).toBe('true');
    auth = { ...auth, preferenceSubject: null };
    hook.rerender();
    expect(hook.result.current.hidden).toBe(false);
    expect(hook.result.current.ready).toBe(false);
    auth = { ...auth, preferenceSubject: 'original' };
    hook.rerender();
    expect(hook.result.current.hidden).toBe(true);
    act(() => hook.result.current.setHidden(false));
    expect(storage.has(key)).toBe(false);
  });

  it('fails visible for unresolved auth and accepts only explicitly verified auth-off storage', () => {
    const applianceKey = prefix + 'appliance:printer:serial-a';
    storage.set(applianceKey, 'true');
    auth = { ...auth, authEnabled: false, authStatusVerified: false, preferenceSubject: null };
    const hook = renderHook(() => useExternalSpoolDisplay('serial-a'));
    expect(hook.result.current.hidden).toBe(false);
    expect(hook.result.current.ready).toBe(false);
    act(() => hook.result.current.setHidden(false));
    expect(storage.get(applianceKey)).toBe('true');
    auth = { ...auth, authStatusVerified: true };
    hook.rerender();
    expect(hook.result.current.hidden).toBe(true);
    auth = { ...auth, loading: true };
    hook.rerender();
    expect(hook.result.current.hidden).toBe(false);
    expect(hook.result.current.ready).toBe(false);
  });

  it.each([undefined, '', '   '])('fails visible and disallows persistence for missing serial %s', serial => {
    const hook = renderHook(() => useExternalSpoolDisplay(serial));
    act(() => hook.result.current.setHidden(true));
    expect(hook.result.current.hidden).toBe(false);
    expect(hook.result.current.ready).toBe(false);
    expect(storage.size).toBe(0);
  });

  it.each(['false', '1', '{}', 'TRUE'])('ignores corrupt value %s', value => {
    storage.set(key, value);
    const hook = renderHook(() => useExternalSpoolDisplay('serial-a'));
    expect(hook.result.current.hidden).toBe(false);
  });

  it('updates other mounted cards and responds to cross-tab changes and storage clearing', () => {
    const first = renderHook(() => useExternalSpoolDisplay('serial-a'));
    const second = renderHook(() => useExternalSpoolDisplay('serial-a'));
    act(() => first.result.current.setHidden(true));
    expect(second.result.current.hidden).toBe(true);
    storage.delete(key);
    act(() => window.dispatchEvent(new StorageEvent('storage', { key })));
    expect(first.result.current.hidden).toBe(false);
    storage.set(key, 'true');
    act(() => window.dispatchEvent(new StorageEvent('storage', { key })));
    expect(second.result.current.hidden).toBe(true);
    storage.clear();
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: null })));
    expect(second.result.current.hidden).toBe(false);
  });

  it('keeps blocked-storage recovery usable and isolated by account and printer', () => {
    auth = { ...auth, preferenceSubject: 'blocked' };
    vi.mocked(localStorage.getItem).mockImplementation(() => { throw Error('blocked'); });
    vi.mocked(localStorage.setItem).mockImplementation(() => { throw Error('blocked'); });
    vi.mocked(localStorage.removeItem).mockImplementation(() => { throw Error('blocked'); });
    const hook = renderHook(({ serial }) => useExternalSpoolDisplay(serial), { initialProps: { serial: 'serial-a' } });
    act(() => hook.result.current.setHidden(true));
    expect(hook.result.current.hidden).toBe(true);
    hook.rerender({ serial: 'serial-b' });
    expect(hook.result.current.hidden).toBe(false);
    hook.rerender({ serial: 'serial-a' });
    expect(hook.result.current.hidden).toBe(true);
    auth = { ...auth, preferenceSubject: 'other' };
    hook.rerender({ serial: 'serial-a' });
    expect(hook.result.current.hidden).toBe(false);
    auth = { ...auth, preferenceSubject: 'blocked' };
    hook.rerender({ serial: 'serial-a' });
    act(() => hook.result.current.setHidden(false));
    expect(hook.result.current.hidden).toBe(false);
  });
});

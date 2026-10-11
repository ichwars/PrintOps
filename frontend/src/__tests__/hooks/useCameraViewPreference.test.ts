import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useCameraViewPreference } from '../../hooks/useCameraViewPreference';

let auth: { authEnabled: boolean; loading: boolean; user: { id: number } | null };
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => auth }));

const userOneKey = 'printops:camera-view:v1:http%3A%2F%2Flocalhost%3A3000:user:1:7';
const userTwoKey = 'printops:camera-view:v1:http%3A%2F%2Flocalhost%3A3000:user:2:7';
const applianceKey = 'printops:camera-view:v1:http%3A%2F%2Flocalhost%3A3000:appliance:7';

describe('camera preference identity and storage boundaries', () => {
  let storage: Map<string, string>;
  beforeEach(() => {
    auth = { authEnabled: true, loading: false, user: { id: 1 } };
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

  it('restores each user and printer separately with no old-user render during a switch', () => {
    const renders: string[] = [];
    const hook = renderHook(({ id }) => {
      const preference = useCameraViewPreference(id);
      renders.push(preference.mode);
      return preference;
    }, { initialProps: { id: 7 } });
    act(() => hook.result.current.setPreference('snapshot'));
    expect(storage.get(userOneKey)).toBe('{"version":1,"mode":"snapshot"}');

    const switchStart = renders.length;
    auth = { ...auth, user: { id: 2 } };
    hook.rerender({ id: 7 });
    expect(renders.slice(switchStart)).not.toContain('snapshot');
    expect(hook.result.current.mode).toBe('stream');
    expect(hook.result.current.preference).toBeNull();
    expect(storage.has(userTwoKey)).toBe(false);
    act(() => hook.result.current.setPreference('snapshot'));
    hook.rerender({ id: 8 });
    expect(hook.result.current.mode).toBe('stream');
    auth = { ...auth, user: { id: 1 } };
    hook.rerender({ id: 7 });
    expect(hook.result.current.mode).toBe('snapshot');
  });

  it('waits for auth resolution before using the explicitly local appliance scope', () => {
    storage.set(applianceKey, '{"version":1,"mode":"snapshot"}');
    auth = { authEnabled: false, loading: true, user: null };
    const hook = renderHook(() => useCameraViewPreference(7));
    expect(hook.result.current.ready).toBe(false);
    expect(hook.result.current.mode).toBe('stream');
    act(() => hook.result.current.setPreference('stream'));
    expect(storage.get(applianceKey)).toBe('{"version":1,"mode":"snapshot"}');
    auth = { ...auth, loading: false };
    hook.rerender();
    expect(hook.result.current.mode).toBe('snapshot');
    auth = { authEnabled: true, loading: false, user: { id: 1 } };
    hook.rerender();
    expect(hook.result.current.mode).toBe('stream');
  });

  it('never reads or writes a signed-in default through an anonymous camera link', () => {
    storage.set(userOneKey, '{"version":1,"mode":"snapshot"}');
    const hook = renderHook(({ anonymous }) => useCameraViewPreference(7, { anonymous }), { initialProps: { anonymous: true } });
    expect(hook.result.current.mode).toBe('stream');
    act(() => hook.result.current.setPreference('snapshot'));
    act(() => hook.result.current.setPreference('stream'));
    expect(storage.get(userOneKey)).toBe('{"version":1,"mode":"snapshot"}');
    hook.rerender({ anonymous: false });
    expect(hook.result.current.mode).toBe('snapshot');
    hook.rerender({ anonymous: true });
    expect(hook.result.current.mode).toBe('stream');
  });

  it('keeps signed-out selections transient and resets them on identity change', () => {
    auth = { authEnabled: true, loading: false, user: null };
    const hook = renderHook(() => useCameraViewPreference(7));
    act(() => hook.result.current.setPreference('snapshot'));
    expect(hook.result.current.mode).toBe('snapshot');
    expect(storage.size).toBe(0);
    auth = { ...auth, user: { id: 2 } };
    hook.rerender();
    expect(hook.result.current.mode).toBe('stream');
    auth = { ...auth, user: null };
    hook.rerender();
    expect(hook.result.current.mode).toBe('stream');
  });

  it.each(['{invalid', 'null', '[]', '{"version":2,"mode":"snapshot"}', '{"version":1,"mode":"file:///secret"}'])(
    'uses the stream default for invalid saved data: %s', (value) => {
      storage.set(userOneKey, value);
      const hook = renderHook(() => useCameraViewPreference(7));
      expect(hook.result.current.mode).toBe('stream');
      act(() => hook.result.current.setPreference('snapshot'));
      expect(hook.result.current.mode).toBe('snapshot');
      act(() => hook.result.current.setPreference(null));
      expect(hook.result.current.mode).toBe('stream');
      expect(storage.has(userOneKey)).toBe(false);
    },
  );

  it('keeps a blocked-storage selection usable and scoped to its user and printer', () => {
    auth = { ...auth, user: { id: 71 } };
    vi.mocked(localStorage.getItem).mockImplementation(() => { throw new Error('blocked'); });
    vi.mocked(localStorage.setItem).mockImplementation(() => { throw new Error('blocked'); });
    vi.mocked(localStorage.removeItem).mockImplementation(() => { throw new Error('blocked'); });
    const hook = renderHook(({ id }) => useCameraViewPreference(id), { initialProps: { id: 7 } });
    act(() => hook.result.current.setPreference('snapshot'));
    expect(hook.result.current.mode).toBe('snapshot');
    hook.rerender({ id: 8 });
    expect(hook.result.current.mode).toBe('stream');
    auth = { ...auth, user: { id: 72 } };
    hook.rerender({ id: 7 });
    expect(hook.result.current.mode).toBe('stream');
    auth = { ...auth, user: { id: 71 } };
    hook.rerender({ id: 7 });
    expect(hook.result.current.mode).toBe('snapshot');
    act(() => hook.result.current.setPreference(null));
    expect(hook.result.current.mode).toBe('stream');
  });

  it('updates an already-open viewer and handles a reset from another tab', () => {
    const card = renderHook(() => useCameraViewPreference(7));
    const viewer = renderHook(() => useCameraViewPreference(7));
    act(() => card.result.current.setPreference('snapshot'));
    expect(viewer.result.current.mode).toBe('snapshot');
    storage.delete(userOneKey);
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: userOneKey })));
    expect(viewer.result.current.mode).toBe('stream');
  });
  it.each(['stream', null] as const)('releases a launch hint after the matching card changes its default to %s', (value) => {
    const card = renderHook(() => useCameraViewPreference(7));
    const popup = renderHook(() => useCameraViewPreference(7, { initialMode: 'snapshot' }));
    expect(popup.result.current.mode).toBe('snapshot');
    expect(storage.has(userOneKey)).toBe(false);
    act(() => card.result.current.setPreference(value));
    expect(popup.result.current.mode).toBe('stream');
    expect(popup.result.current.preference).toBe(value);
  });

  it('releases a launch hint for a matching storage reset but ignores another user or printer', () => {
    const popup = renderHook(() => useCameraViewPreference(7, { initialMode: 'snapshot' }));
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: userTwoKey })));
    expect(popup.result.current.mode).toBe('snapshot');
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: userOneKey.replace(':7', ':8') })));
    expect(popup.result.current.mode).toBe('snapshot');
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: userOneKey })));
    expect(popup.result.current.mode).toBe('stream');
  });

});

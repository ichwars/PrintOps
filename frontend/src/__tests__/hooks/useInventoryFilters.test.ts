import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuth } from '../../contexts/AuthContext';
import { useInventoryFilters } from '../../hooks/useInventoryFilters';
import { inventoryFilterScope } from '../../utils/inventoryFilterPreferences';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));
const saved = new Map<string, string>();
function auth(userId: number | null, authEnabled = true, loading = false) {
  vi.mocked(useAuth).mockReturnValue({ authEnabled, loading,
    user: userId === null ? null : { id: userId },
  } as ReturnType<typeof useAuth>);
}

beforeEach(() => {
  saved.clear();
  auth(1);
  vi.mocked(localStorage.getItem).mockImplementation(key => saved.get(key) ?? null);
  vi.mocked(localStorage.setItem).mockImplementation((key, value) => { saved.set(key, value); });
  vi.mocked(localStorage.removeItem).mockImplementation(key => { saved.delete(key); });
});
afterEach(() => {
  vi.mocked(localStorage.getItem).mockReset();
  vi.mocked(localStorage.setItem).mockReset();
  vi.mocked(localStorage.removeItem).mockReset();
});

describe('scoped inventory filters', () => {
  it('switches identity without rendering another user search and restores each user on return', () => {
    const { result, rerender } = renderHook(() => useInventoryFilters(false, false));
    act(() => result.current.setFilter('search', 'user one'));
    auth(2);
    rerender();
    expect(result.current.filters.search).toBe('');
    act(() => result.current.setFilter('search', 'user two'));
    auth(null);
    rerender();
    expect(result.current.filters.search).toBe('');
    auth(1);
    rerender();
    expect(result.current.filters.search).toBe('user one');
    auth(2);
    rerender();
    expect(result.current.filters.search).toBe('user two');
  });

  it('keeps local and Spoolman inventory preferences separate', () => {
    const { result, rerender } = renderHook(({ spoolman }) => useInventoryFilters(spoolman, false), {
      initialProps: { spoolman: false },
    });
    act(() => result.current.setFilter('materialFilter', 'PLA'));
    rerender({ spoolman: true });
    expect(result.current.filters.materialFilter).toBe('');
    act(() => result.current.setFilter('materialFilter', 'PETG'));
    rerender({ spoolman: false });
    expect(result.current.filters.materialFilter).toBe('PLA');
  });

  it('applies batched filter changes together and restores them after a remount', () => {
    const first = renderHook(() => useInventoryFilters(false, false));
    act(() => {
      first.result.current.setFilter('archiveFilter', 'archived');
      first.result.current.setFilter('usageFilter', 'used');
      first.result.current.setFilter('brandFilter', 'Example');
      first.result.current.setFilter('spoolFilter', '42');
      first.result.current.setFilter('stockFilter', 'configured');
      first.result.current.setFilter('categoryFilter', 'Production');
    });
    first.unmount();
    const next = renderHook(() => useInventoryFilters(false, false));
    expect(next.result.current.filters).toMatchObject({ archiveFilter: 'archived', usageFilter: 'used',
      brandFilter: 'Example', spoolFilter: '42', stockFilter: 'configured', categoryFilter: 'Production' });
  });

  it('gives deep links precedence without overwriting the ordinary preference, even after URL removal', () => {
    const first = renderHook(() => useInventoryFilters(false, false));
    act(() => first.result.current.setFilter('search', 'ordinary view'));
    first.unmount();
    const link = renderHook(({ override }) => useInventoryFilters(false, override), { initialProps: { override: true } });
    expect(link.result.current.filters.search).toBe('');
    act(() => link.result.current.setFilter('search', 'linked view'));
    link.rerender({ override: false });
    act(() => link.result.current.resetFilters());
    link.unmount();
    const ordinary = renderHook(() => useInventoryFilters(false, false));
    expect(ordinary.result.current.filters.search).toBe('ordinary view');
  });

  it('a new link on the mounted route overrides previously restored filters', () => {
    const { result, rerender } = renderHook(({ override }) => useInventoryFilters(false, override), {
      initialProps: { override: false },
    });
    act(() => result.current.setFilter('search', 'saved'));
    rerender({ override: true });
    expect(result.current.filters.search).toBe('');
  });

  it('preserves visible filters while choosing a location without persisting later location-view changes', () => {
    const { result, rerender } = renderHook(({ override }) => useInventoryFilters(false, override), {
      initialProps: { override: false },
    });
    act(() => result.current.setFilter('search', 'saved'));
    act(() => result.current.beginTransientView());
    rerender({ override: true });
    expect(result.current.filters.search).toBe('saved');
    act(() => result.current.setFilter('search', 'location-only'));
    const scope = inventoryFilterScope(true, 1, false, false)!;
    expect(JSON.parse(saved.get(scope)!).filters.search).toBe('saved');
  });

  it('never restores an authenticated preference during bootstrap or in the auth-disabled appliance scope', () => {
    const first = renderHook(() => useInventoryFilters(false, false));
    act(() => first.result.current.setFilter('search', 'private user view'));
    auth(null, false, true);
    first.rerender();
    expect(first.result.current.filters.search).toBe('');
    auth(null, false, false);
    first.rerender();
    expect(first.result.current.filters.search).toBe('');
  });

  it.each(['{broken', '{"version":2,"filters":{"search":"obsolete"}}',
    '{"version":1,"filters":{"usageFilter":"invalid","stockFilter":5,"spoolFilter":"-1","search":{}}}'])(
    'ignores malformed, obsolete and invalid filter records: %s', raw => {
    saved.set(inventoryFilterScope(true, 1, false, false)!, raw);
    const { result } = renderHook(() => useInventoryFilters(false, false));
    expect(result.current.filters.search).toBe('');
    expect(result.current.filters.usageFilter).toBe('all');
    expect(result.current.filters.stockFilter).toBe('all');
    expect(result.current.filters.spoolFilter).toBe('');
    },
  );

  it('keeps the current view usable when browser storage is denied', () => {
    vi.mocked(localStorage.getItem).mockImplementation(() => { throw new Error('denied'); });
    vi.mocked(localStorage.setItem).mockImplementation(() => { throw new Error('denied'); });
    vi.mocked(localStorage.removeItem).mockImplementation(() => { throw new Error('denied'); });
    const { result } = renderHook(() => useInventoryFilters(false, false));
    act(() => result.current.setFilter('search', 'still usable'));
    expect(result.current.filters.search).toBe('still usable');
    act(() => result.current.resetFilters());
    expect(result.current.filters.search).toBe('');
  });
});

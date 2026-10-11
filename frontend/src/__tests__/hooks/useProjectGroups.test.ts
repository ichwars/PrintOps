import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useProjectGroups } from '../../hooks/useProjectGroups';

describe('project group preferences', () => {
  let storage: Map<string, string>;
  beforeEach(() => {
    storage = new Map();
    vi.mocked(localStorage.getItem).mockImplementation(key => storage.get(key) ?? null);
    vi.mocked(localStorage.setItem).mockImplementation((key, value) => { storage.set(key, value); });
  });
  afterEach(() => {
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.setItem).mockReset();
  });

  it('persists the default across reload while overrides apply to the current view', () => {
    const first = renderHook(() => useProjectGroups(1));
    act(() => first.result.current.setDefaultCollapsed(true));
    expect(first.result.current.isExpanded(7)).toBe(false);
    act(() => first.result.current.toggle(7));
    expect(first.result.current.isExpanded(7)).toBe(true);
    first.unmount();
    const second = renderHook(() => useProjectGroups(1));
    expect(second.result.current.defaultCollapsed).toBe(true);
    expect(second.result.current.isExpanded(7)).toBe(false);
  });

  it('isolates defaults and local overrides when the user changes', () => {
    const { result, rerender } = renderHook(({ id }) => useProjectGroups(id), { initialProps: { id: 1 as number | null } });
    act(() => result.current.setDefaultCollapsed(true));
    act(() => result.current.toggle(7));
    rerender({ id: 2 });
    expect(result.current.defaultCollapsed).toBe(false);
    expect(result.current.isExpanded(8)).toBe(true);
    act(() => result.current.toggle(7));
    rerender({ id: null });
    expect(result.current.defaultCollapsed).toBe(false);
    expect(result.current.isExpanded(7)).toBe(true);
    rerender({ id: 1 });
    expect(result.current.defaultCollapsed).toBe(true);
    expect(result.current.isExpanded(7)).toBe(true);
  });

  it('applies a changed global default to all groups and clears local deviations', () => {
    const { result } = renderHook(() => useProjectGroups(1));
    act(() => result.current.toggle(7));
    expect(result.current.isExpanded(7)).toBe(false);
    act(() => result.current.setDefaultCollapsed(false));
    expect(result.current.isExpanded(7)).toBe(true);
    expect(result.current.isExpanded(8)).toBe(true);
  });

  it('stays usable when browser storage is blocked or invalid', () => {
    storage.set('printops-project-groups:1', 'invalid');
    const { result } = renderHook(() => useProjectGroups(1));
    expect(result.current.defaultCollapsed).toBe(false);
    vi.mocked(localStorage.getItem).mockImplementation(() => { throw new Error('storage disabled'); });
    vi.mocked(localStorage.setItem).mockImplementation(() => { throw new Error('storage disabled'); });
    act(() => result.current.setDefaultCollapsed(true));
    expect(result.current.isExpanded(7)).toBe(false);
    act(() => result.current.toggle(7));
    expect(result.current.isExpanded(7)).toBe(true);
  });
});

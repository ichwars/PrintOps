import { useState } from 'react';

/** Per-user, per-browser default; group overrides last for the current view. */
export function useProjectGroups(userId: number | null) {
  const key = `printops-project-groups:${userId ?? 'anonymous'}`;
  const [defaults, setDefaults] = useState<Record<string, boolean>>({});
  const [overrides, setOverrides] = useState<Record<string, Record<number, boolean>>>({});
  let stored = false;
  try { stored = localStorage.getItem(key) === 'true'; } catch { /* Storage may be disabled. */ }
  const defaultCollapsed = defaults[key] ?? stored;

  const setDefaultCollapsed = (collapsed: boolean) => {
    setDefaults(previous => ({ ...previous, [key]: collapsed }));
    setOverrides(previous => ({ ...previous, [key]: {} }));
    try { localStorage.setItem(key, String(collapsed)); } catch { /* Keep the view usable without storage. */ }
  };
  const isExpanded = (id: number) => overrides[key]?.[id] ?? !defaultCollapsed;
  const toggle = (id: number) => {
    setOverrides(previous => ({
      ...previous,
      [key]: { ...previous[key], [id]: !(previous[key]?.[id] ?? !defaultCollapsed) },
    }));
  };
  return { defaultCollapsed, setDefaultCollapsed, isExpanded, toggle };
}

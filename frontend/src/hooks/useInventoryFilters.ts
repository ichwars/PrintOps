import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
  defaultInventoryFilters, inventoryFilterScope, loadInventoryFilters, saveInventoryFilters,
  type InventoryFilters,
} from '../utils/inventoryFilterPreferences';

interface FilterSession {
  scope: string | null;
  transient: boolean;
  filters: InventoryFilters;
}

// URL-driven dashboard/location/edit visits have their own view and never
// overwrite ordinary saved filters. Leaving and returning restores those filters.
export function useInventoryFilters(spoolmanMode: boolean, hasURLOverride: boolean) {
  const { authEnabled, user, loading } = useAuth();
  const scope = inventoryFilterScope(authEnabled, user?.id, loading, spoolmanMode);
  const initialSession = (): FilterSession => ({
    scope, transient: hasURLOverride,
    filters: hasURLOverride ? { ...defaultInventoryFilters } : loadInventoryFilters(scope),
  });
  const [session, setSession] = useState(initialSession);
  let active = session;
  if (session.scope !== scope) {
    active = initialSession();
    setSession(active);
  } else if (hasURLOverride && !session.transient) {
    // A new deep link on the same mounted route takes precedence immediately.
    active = { scope, transient: true, filters: { ...defaultInventoryFilters } };
    setSession(active);
  }

  useEffect(() => {
    if (session.scope === scope && !session.transient && !hasURLOverride) {
      saveInventoryFilters(scope, session.filters);
    }
  }, [session, scope, hasURLOverride]);

  const setFilter = useCallback(<K extends keyof InventoryFilters>(key: K, value: InventoryFilters[K]) => {
    setSession(previous => previous.scope === scope
      ? { ...previous, filters: { ...previous.filters, [key]: value } }
      : previous);
  }, [scope]);

  const resetFilters = useCallback(() => {
    setSession(previous => previous.scope === scope
      ? { ...previous, filters: { ...defaultInventoryFilters } }
      : previous);
  }, [scope]);

  // A manually chosen location preserves the filters already visible, while
  // changing to the same transient URL behavior as an incoming location link.
  const beginTransientView = useCallback(() => {
    setSession(previous => previous.scope === scope ? { ...previous, transient: true } : previous);
  }, [scope]);

  return { filters: active.filters, setFilter, resetFilters, beginTransientView };
}

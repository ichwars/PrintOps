import { useCallback, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router';
import { ApiError, api, type InventorySpool } from '../api/client';
import { useToast } from '../contexts/ToastContext';

export function useInventorySpoolDeepLink(
  linkedSpoolId: number | null,
  spoolmanMode: boolean,
  spoolmanModeReady: boolean,
  spools: InventorySpool[] | undefined,
  openSpool: (entry: { spool: InventorySpool; mode: 'edit' }) => void,
) {
  const [searchParams, setSearchParams] = useSearchParams();
  const { t } = useTranslation();
  const { showToast } = useToast();
  const deepLinkHandled = useRef(false);
  const source = searchParams.get('source');
  const wrongInventory = linkedSpoolId !== null && (source === 'inventory' || source === 'spoolman')
    && (source === 'spoolman') !== spoolmanMode;
  const deepLinkSpoolId = wrongInventory ? null : linkedSpoolId;

  // Prefer the already-loaded spool list (no extra API call); fall back to a
  // targeted fetch for the rare case where the full list hasn't arrived yet.
  const deepLinkInList = spools?.find((s) => s.id === deepLinkSpoolId) ?? null;

  const clearDeepLinkParam = useCallback(() => {
    deepLinkHandled.current = true;
    setSearchParams((prev) => { prev.delete('spool'); prev.delete('source'); return prev; }, { replace: true });
  }, [setSearchParams]);

  // Targeted fetch — only fires when mode is known and spool isn't in the list yet
  const { data: deepLinkSpool, isError: deepLinkFetchFailed, error: deepLinkError } = useQuery({
    queryKey: spoolmanMode
      ? ['spoolman-inventory-spool', deepLinkSpoolId]
      : ['inventory-spool', deepLinkSpoolId],
    queryFn: () =>
      spoolmanMode
        ? api.getSpoolmanInventorySpool(deepLinkSpoolId!)
        : api.getSpool(deepLinkSpoolId!),
    enabled: spoolmanModeReady && deepLinkSpoolId !== null && deepLinkInList === null,
    staleTime: Infinity,
    retry: (failureCount, error) =>
      failureCount < 2 && !(error instanceof ApiError && error.status === 404),
  });

  useEffect(() => {
    if (deepLinkHandled.current) return;
    if (spoolmanModeReady && wrongInventory) {
      clearDeepLinkParam();
      showToast(t('inventory.qrAssign.wrongInventory'), 'error');
      return;
    }

    // Case 1: spool is already in the fetched list
    if (spoolmanModeReady && deepLinkSpoolId && deepLinkInList) {
      clearDeepLinkParam();
      openSpool({ spool: deepLinkInList, mode: 'edit' });
      return;
    }

    // Case 2: spool was fetched individually
    if (deepLinkSpool) {
      clearDeepLinkParam();
      openSpool({ spool: deepLinkSpool, mode: 'edit' });
      return;
    }

    // Case 3: fetch failed
    if (deepLinkFetchFailed) {
      clearDeepLinkParam();
      const is404 = deepLinkError instanceof ApiError && deepLinkError.status === 404;
      showToast(t(is404 ? 'inventory.deepLinkSpoolNotFound' : 'inventory.deepLinkFetchFailed'), 'error');
    }
  }, [
    spoolmanModeReady,
    wrongInventory,
    deepLinkSpoolId,
    deepLinkInList,
    deepLinkSpool,
    deepLinkFetchFailed,
    deepLinkError,
    clearDeepLinkParam,
    openSpool,
    showToast,
    t,
  ]);
}

import { useMemo, useState, useSyncExternalStore } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  api, getAuthSessionId, subscribeAuthSession,
  type LoadedSpoolPrinter, type UnifiedPreset, type UnifiedPresetsResponse,
} from '../api/client';
import {
  buildFilamentNameIndex, isConnectedModelPreset, isLoaded, matchSlotPreset,
  pickConnectedPrinterPreset, printerPresetModel, printersOfModel,
} from '../utils/sliceLoadedSpools';
import type { PrinterCompatibilityIndex } from '../utils/slicerPrinterMatch';

const NO_PRINTERS: LoadedSpoolPrinter[] = [];

function useFilterPreference(name: string) {
  const key = `printops:slice:${name}`;
  const [checked, setChecked] = useState(() => {
    try { return localStorage.getItem(key) === 'true'; } catch { return false; }
  });
  const update = (value: boolean) => {
    setChecked(value);
    try { localStorage.setItem(key, String(value)); } catch { /* Browser storage may be unavailable. */ }
  };
  return [checked, update] as const;
}

export function useSliceLoadedSpools(
  data: UnifiedPresetsResponse | undefined,
  printerName: string | null,
  printerModels: Record<string, string> | undefined,
  compatIndex: PrinterCompatibilityIndex,
) {
  const authSession = useSyncExternalStore(subscribeAuthSession, getAuthSessionId);
  const [onlineOnly, setOnlineOnly] = useFilterPreference('online-only');
  const [loadedOnly, setLoadedOnly] = useFilterPreference('loaded-only');
  const query = useQuery({
    queryKey: ['slicerLoadedSpools', authSession],
    queryFn: api.getSlicerLoadedSpools,
    enabled: data !== undefined,
    staleTime: 15_000,
    gcTime: 0,
    retry: false,
  });
  const printers = query.isSuccess ? query.data.printers : NO_PRINTERS;

  const groups = useMemo(() => {
    if (!data || printers.length === 0) return [];
    const names = [...(compatIndex.printerParents ?? [])].reverse();
    if (printerName) names.push(printerName);
    const model = printerPresetModel(names, printerModels ?? {});
    const index = buildFilamentNameIndex(data);
    return printersOfModel(printers, model).map((printer) => ({
      printer,
      spools: [...printer.ams.flatMap((unit) => unit.trays), ...printer.external]
        .filter(isLoaded)
        .map((tray) => ({ tray, match: matchSlotPreset(tray, data, index, printerName, compatIndex) })),
    }));
  }, [data, printers, printerModels, printerName, compatIndex]);

  const online = useMemo(() => {
    if (!onlineOnly || !data || !printerModels || !printers.some((printer) => printer.model)) return null;
    const models = printers.map((printer) => printer.model);
    const filter = (preset: UnifiedPreset) => isConnectedModelPreset(data, preset, models, printerModels);
    return { filter, preferred: pickConnectedPrinterPreset(data, models, printerModels) };
  }, [onlineOnly, data, printerModels, printers]);

  const loaded = useMemo(() => {
    if (!loadedOnly || !data) return null;
    const refs = new Set(groups.flatMap(({ spools }) => spools.flatMap(({ match }) =>
      match ? [`${match.ref.source}:${match.ref.id}`] : [],
    )));
    if (refs.size === 0) return null;
    const filter = (preset: UnifiedPreset) => refs.has(`${preset.source}:${preset.id}`);
    return {
      filter,
      data: {
        ...data,
        local: { ...data.local, filament: data.local.filament.filter(filter) },
        orca_cloud: { ...data.orca_cloud, filament: data.orca_cloud.filament.filter(filter) },
        cloud: { ...data.cloud, filament: data.cloud.filament.filter(filter) },
        standard: { ...data.standard, filament: data.standard.filament.filter(filter) },
      },
    };
  }, [data, groups, loadedOnly]);

  return { available: query.isSuccess, printers, groups, onlineOnly, setOnlineOnly, online, loadedOnly, setLoadedOnly, loaded };
}

import { useEffect, useState } from 'react';
import { api, type SpoolFilamentPreset } from '../../api/client';

export function useModelPresets(isOpen: boolean, sourceId: number | undefined, spoolman: boolean) {
  const [presets, setPresets] = useState<SpoolFilamentPreset[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [touched, setTouched] = useState(false);
  const [loading, setLoading] = useState(!!sourceId);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  const [loadedFor, setLoadedFor] = useState('');
  const context = `${spoolman}:${sourceId ?? 'new'}`;
  const pending = loading || (!!sourceId && loadedFor !== context && !error);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setPresets([]);
    setTouched(false);
    setError(false);
    setLoading(!!sourceId);
    setLoadedFor('');
    api.getSlicerPrinterModels().then(registry => {
      if (!cancelled) setModels([...new Set(Object.values(registry))].sort());
    }).catch(() => { if (!cancelled) setModels([]); });
    if (sourceId) {
      const get = spoolman ? api.getSpoolmanFilamentPresets : api.getSpoolFilamentPresets;
      get(sourceId).then(rows => {
        if (!cancelled) { setPresets(rows); setLoadedFor(`${spoolman}:${sourceId}`); }
      }).catch(() => {
        if (!cancelled) setError(true);
      }).finally(() => {
        if (!cancelled) setLoading(false);
      });
    }
    return () => { cancelled = true; };
  }, [isOpen, sourceId, spoolman, revision]);

  const update = (rows: SpoolFilamentPreset[]) => { setPresets(rows); setTouched(true); };
  const save = async (targetId: number) => {
    // Ordinary edits never replace a map that the user has not changed.
    if (!touched && targetId === sourceId) return;
    if (sourceId && (pending || error || loadedFor !== context)) throw new Error('Preset overrides were not loaded');
    if (!touched && presets.length === 0) return;
    const put = spoolman ? api.saveSpoolmanFilamentPresets : api.saveSpoolFilamentPresets;
    await put(targetId, presets);
  };

  return { presets, models, touched, loading: pending, error, update, save, retry: () => setRevision(v => v + 1) };
}

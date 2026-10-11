import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { SpoolFilamentPreset } from '../../api/client';
import { Button } from '../Button';
import { Select } from '../ui/Select';
import type { FilamentOption, PrinterWithCalibrations } from './types';

interface Props {
  models: string[];
  presets: SpoolFilamentPreset[];
  printers: PrinterWithCalibrations[];
  filamentOptions: FilamentOption[];
  loading: boolean;
  error: boolean;
  retry: () => void;
  onChange: (presets: SpoolFilamentPreset[]) => void;
}

export function ModelPresetSection({ models, presets, printers, filamentOptions, loading, error, retry, onChange }: Props) {
  const { t } = useTranslation();
  const [added, setAdded] = useState<string[]>([]);
  const visible = [...new Set([
    ...printers.map(p => p.printer.model).filter((m): m is string => !!m && models.includes(m)),
    ...presets.map(p => p.printer_model), ...added,
  ])].sort();

  const changePreset = (model: string, value: string) => {
    const others = presets.filter(p => p.printer_model !== model);
    if (value === 'inherit') { onChange(others); return; }
    const code = value === 'generic' ? null : value.slice(7);
    const option = filamentOptions.find(p => p.code === code);
    onChange([...others, {
      printer_model: model, slicer_filament: code,
      slicer_filament_name: option?.name ?? (code ? presets.find(p => p.printer_model === model)?.slicer_filament_name ?? null : null),
    }].sort((a, b) => a.printer_model.localeCompare(b.printer_model)));
  };

  return (
    <section className="space-y-3 mb-6">
      <h3 className="text-sm font-semibold text-bambu-gray uppercase tracking-wide">{t('inventory.modelPresetsTitle')}</h3>
      <p className="text-sm text-bambu-gray">{t('inventory.modelPresetsHelp')}</p>
      {error && <div role="alert" className="text-sm text-red-400">
        {t('inventory.modelPresetsLoadFailed')}
        <Button variant="secondary" onClick={retry}>{t('common.retry')}</Button>
      </div>}
      {visible.map(model => {
        const row = presets.find(p => p.printer_model === model);
        const code = row?.slicer_filament;
        const value = !row ? 'inherit' : !code ? 'generic' : `preset:${code}`;
        const options = [
          { value: 'inherit', label: t('inventory.modelPresetsInherit') },
          { value: 'generic', label: t('inventory.modelPresetsGeneric') },
          ...filamentOptions.map(p => ({ value: `preset:${p.code}`, label: p.displayName })),
        ];
        // Preserve presets which are unavailable while cloud login/imports are absent.
        if (code && !options.some(p => p.value === value)) options.push({ value, label: row.slicer_filament_name || code });
        return <Select key={model} label={model} value={value} options={options}
          disabled={loading || error} onValueChange={v => changePreset(model, v)} />;
      })}
      <Select value="" label={t('inventory.modelPresetsAddModel')}
        options={[{ value: '', label: t('inventory.modelPresetsAddModel') }, ...models.filter(m => !visible.includes(m)).map(m => ({ value: m, label: m }))]}
        disabled={loading || error || models.length === 0} onValueChange={model => { if (model) setAdded(prev => [...prev, model]); }} />
    </section>
  );
}

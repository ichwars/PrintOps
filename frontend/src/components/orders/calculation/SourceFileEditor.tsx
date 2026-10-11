import { resolveSupportedLanguage } from '../../../i18n';
import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { FileUp, X } from 'lucide-react';
import { calculationsApi, type CalculationOperation } from '../../../api/calculations';
import { FileInput } from '../../ui';

export function SourceFileEditor({ operation, locale, onChange }: { operation: CalculationOperation; locale: string; onChange: (operation: CalculationOperation) => void }) {
  const language = resolveSupportedLanguage(locale);
  const { t } = useTranslation(undefined, { lng: language });
  const [uploading, setUploading] = useState(false);
  const select = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    try {
      const imported = await calculationsApi.uploadSource(file);
      onChange({ ...operation, source_file: imported.source_file, source_plate: imported.plate_count === 1 ? 1 : operation.source_plate, material_grams_per_run: imported.material_grams > 0 ? String(imported.material_grams) : operation.material_grams_per_run, print_hours_per_run: imported.print_time_seconds ? String(imported.print_time_seconds / 3600) : operation.print_hours_per_run, provenance: { ...operation.provenance, source: '3mf', filename: imported.filename, plate_count: imported.plate_count, material_grams: imported.material_grams, imported_at: new Date().toISOString() } });
    } finally { setUploading(false); }
  };
  return <div className="lg:col-span-7">
    {operation.source_file ? <div className="flex items-center justify-between rounded-lg border border-bambu-green/30 bg-bambu-green/5 px-3 py-2 text-sm"><div><span className="font-medium text-white">{String(operation.provenance.filename ?? operation.source_file)}</span><span className="ml-2 rounded bg-bambu-dark px-2 py-0.5 text-xs text-bambu-gray">3MF · {Number(operation.provenance.plate_count ?? 0)} {t('projects.plates', { lng: language })} · {Number(operation.provenance.material_grams ?? 0).toFixed(1)} g</span></div><button aria-label={t('orders.runtimeCalculation.removeFileAssociation', { lng: language })} onClick={() => onChange({ ...operation, source_file: null, provenance: { source: 'manual' } })} className="text-bambu-gray hover:text-white"><X className="h-4 w-4" /></button></div> : <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-dashed border-bambu-dark-tertiary px-3 py-2 text-sm text-bambu-gray hover:border-bambu-green hover:text-white"><FileUp className="h-4 w-4" />{uploading ? (t('orders.runtimeCalculation.importing3MF', { lng: language })) : (t('orders.runtimeCalculation.uploadAndAnalyze3MF', { lng: language }))}<FileInput accept=".3mf,model/3mf" disabled={uploading} className="sr-only" onChange={e => void select(e.target.files?.[0])} /></label>}
  </div>;
}

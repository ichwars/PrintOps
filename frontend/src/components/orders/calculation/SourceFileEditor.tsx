import { FileUp, X } from 'lucide-react';
import type { CalculationOperation } from '../../../api/calculations';

export function SourceFileEditor({ operation, locale, onChange }: { operation: CalculationOperation; locale: string; onChange: (operation: CalculationOperation) => void }) {
  const de = locale.startsWith('de');
  const select = (file: File | undefined) => {
    if (!file) return;
    onChange({ ...operation, source_file: file.name, provenance: { ...operation.provenance, source: 'file', filename: file.name, size_bytes: file.size, imported_at: new Date().toISOString() } });
  };
  return <div className="lg:col-span-7">
    {operation.source_file ? <div className="flex items-center justify-between rounded-lg border border-bambu-green/30 bg-bambu-green/5 px-3 py-2 text-sm"><div><span className="font-medium text-white">{operation.source_file}</span><span className="ml-2 rounded bg-bambu-dark px-2 py-0.5 text-xs text-bambu-gray">{de ? 'Dateiquelle' : 'File source'}{operation.source_plate != null ? ` · ${de ? 'Platte' : 'Plate'} ${operation.source_plate}` : ''}</span></div><button aria-label={de ? 'Dateizuordnung entfernen' : 'Remove file association'} onClick={() => onChange({ ...operation, source_file: null, provenance: { source: 'manual' } })} className="text-bambu-gray hover:text-white"><X className="h-4 w-4" /></button></div> : <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-dashed border-bambu-dark-tertiary px-3 py-2 text-sm text-bambu-gray hover:border-bambu-green hover:text-white"><FileUp className="h-4 w-4" />{de ? '3MF/STL als Datenquelle wählen' : 'Select 3MF/STL as data source'}<input type="file" accept=".3mf,.stl,model/3mf" className="sr-only" onChange={e => select(e.target.files?.[0])} /></label>}
  </div>;
}

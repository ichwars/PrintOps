import { useEffect, useMemo, useRef, useState } from 'react';
import { Cpu, Database, FileUp, LoaderCircle, Wind } from 'lucide-react';

import type { Equipment, InventorySpool, Printer } from '../../../api/client';
import { calculationsApi, type CalculationProjectFile, type CalculationProjectPlate, type CalculationVariantPlate } from '../../../api/calculations';
import { formatGrams } from '../../../utils/calculationFormatting';
import { LegacySelect, NumberField, TextField } from '../../ui';
import { ProjectPlateGrid } from './ProjectPlateGrid';

const inputClass = 'mt-1 h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary px-3 text-white outline-none focus:border-bambu-green';

interface ProjectFileSectionProps {
  calculationId: number | null;
  plates: CalculationVariantPlate[];
  printers: Printer[];
  dryers: Equipment[];
  spools: InventorySpool[];
  locale: string;
  onChange: (plates: CalculationVariantPlate[]) => void;
}

function newSelection(plate: CalculationProjectPlate, sortOrder: number): CalculationVariantPlate {
  const material = plate.detected_materials[0];
  return {
    project_plate_id: plate.id,
    good_parts: Math.max(1, plate.object_count),
    parts_per_print: Math.max(1, plate.object_count),
    scrap_prints: 0,
    material_code: String(material?.type ?? material?.name ?? '') || null,
    grams_per_print: plate.detected_grams,
    hours_per_print: plate.detected_hours,
    overrides: {},
    provenance: { source: '3mf', stable_key: plate.stable_key },
    sort_order: sortOrder,
  };
}

export function ProjectFileSection({ calculationId, plates, printers, dryers, spools, locale, onChange }: ProjectFileSectionProps) {
  const de = locale.startsWith('de');
  const fileInput = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<CalculationProjectFile[]>([]);
  const [focusedId, setFocusedId] = useState<number | null>(plates[0]?.project_plate_id ?? null);
  const [uploading, setUploading] = useState(false);
  const [slicing, setSlicing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const allPlates = useMemo(() => files.flatMap((file) => file.plates), [files]);
  const selectedIds = useMemo(() => new Set(plates.map((item) => item.project_plate_id)), [plates]);
  const focusedPlate = allPlates.find((item) => item.id === focusedId) ?? null;
  const focusedSelection = plates.find((item) => item.project_plate_id === focusedId) ?? null;

  useEffect(() => {
    if (!calculationId) return;
    void calculationsApi.projectFiles(calculationId).then((items) => {
      setFiles(items);
      if (!focusedId) setFocusedId(plates[0]?.project_plate_id ?? items.at(-1)?.plates[0]?.id ?? null);
    }).catch((error) => setMessage(error instanceof Error ? error.message : String(error)));
  }, [calculationId]); // eslint-disable-line react-hooks/exhaustive-deps

  const select = (ids: Set<number>) => {
    const existing = new Map(plates.map((item) => [item.project_plate_id, item]));
    onChange(allPlates.filter((item) => ids.has(item.id)).map((item, index) => existing.get(item.id) ?? newSelection(item, index)).map((item, index) => ({ ...item, sort_order: index })));
  };
  const updateFocused = (values: Partial<CalculationVariantPlate>) => {
    if (!focusedId) return;
    onChange(plates.map((item) => item.project_plate_id === focusedId ? { ...item, ...values } : item));
  };
  const upload = async (file?: File) => {
    if (!file || !calculationId) return;
    setUploading(true); setMessage(null);
    try {
      const created = await calculationsApi.uploadProjectFile(calculationId, file);
      setFiles((current) => [...current, created]);
      const additions = created.plates.map((item, index) => newSelection(item, plates.length + index));
      onChange([...plates, ...additions]);
      setFocusedId(created.plates[0]?.id ?? null);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
    finally { setUploading(false); }
  };
  const slice = async () => {
    if (!selectedIds.size) return;
    setSlicing(true); setMessage(null);
    try {
      const results = (await Promise.all(files.map((file) => {
        const ids = file.plates.filter((item) => selectedIds.has(item.id)).map((item) => item.id);
        return ids.length ? calculationsApi.sliceProjectFile(file.id, ids) : Promise.resolve([]);
      }))).flat();
      onChange(plates.map((item) => {
        const result = results.find((candidate) => candidate.project_plate_id === item.project_plate_id);
        return result ? { ...item, grams_per_print: result.material_grams, hours_per_print: result.print_hours, provenance: { ...item.provenance, source: result.source, slice_result_id: result.id, fallback_reason: result.fallback_reason } } : item;
      }));
      const estimates = results.filter((item) => item.source === 'estimate').length;
      setMessage(estimates ? (de ? `${estimates} Platte(n) geschätzt; Sidecar war nicht erreichbar.` : `${estimates} plate(s) estimated; sidecar unavailable.`) : (de ? 'Slicer-Auswertung abgeschlossen.' : 'Slicing completed.'));
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
    finally { setSlicing(false); }
  };
  const setProvenance = (key: string, value: number) => onChange(plates.map((item) => selectedIds.has(item.project_plate_id) ? { ...item, provenance: { ...item.provenance, [key]: value || null } } : item));
  const materialAvailable = focusedSelection?.material_code ? spools.filter((spool) => !spool.archived_at && spool.material.toLowerCase() === focusedSelection.material_code?.toLowerCase()).reduce((sum, spool) => sum + Math.max(0, spool.label_weight - spool.weight_used), 0) : 0;

  return (
    <section className="space-y-3">
      <div>
        <h3 className="font-semibold text-white">3. {de ? 'Projektdatei' : 'Project file'}</h3>
        <p className="text-xs text-bambu-gray">{de ? 'Druckzeit, Material und Positionen werden je ausgewählter 3MF-Platte übernommen.' : 'Print time, material, and line items are derived per selected 3MF plate.'}</p>
      </div>
      <div className="grid gap-3 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-3 sm:grid-cols-3">
        <label className="text-xs text-bambu-gray"><span className="flex items-center gap-1"><Cpu className="h-3.5 w-3.5" />{de ? 'Drucker' : 'Printer'}</span><LegacySelect value={Number(focusedSelection?.provenance.printer_id ?? 0)} onChange={(event) => setProvenance('printer_id', Number(event.target.value))} className={inputClass}><option value={0}>{de ? 'Kein Drucker' : 'No printer'}</option>{printers.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</LegacySelect></label>
        <label className="text-xs text-bambu-gray"><span className="flex items-center gap-1"><Wind className="h-3.5 w-3.5" />{de ? 'Trockner' : 'Dryer'}</span><LegacySelect value={Number(focusedSelection?.provenance.dryer_id ?? 0)} onChange={(event) => setProvenance('dryer_id', Number(event.target.value))} className={inputClass}><option value={0}>{de ? 'Kein Trockner' : 'No dryer'}</option>{dryers.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</LegacySelect></label>
        <label className="text-xs text-bambu-gray">{de ? 'Trocknungsdauer h' : 'Drying hours'}<NumberField min="0" step="0.05" value={String(focusedSelection?.provenance.drying_hours ?? 0)} onChange={(event) => setProvenance('drying_hours', Number(event.target.value))} containerClassName="mt-1" className={inputClass} /></label>
      </div>
      <div onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void upload(event.dataTransfer.files[0]); }} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-bambu-dark-tertiary bg-bambu-dark/50 p-4">
        <div><strong className="text-sm text-white">{de ? '3MF hier ablegen' : 'Drop 3MF here'}</strong><p className="text-xs text-bambu-gray">{calculationId ? (de ? 'oder über den Dateiexplorer auswählen' : 'or select it using the file browser') : (de ? 'Kalkulation zuerst speichern, danach kann die 3MF hochgeladen werden.' : 'Save the calculation before uploading the 3MF.')}</p></div>
        <button type="button" disabled={!calculationId || uploading} onClick={() => fileInput.current?.click()} className="inline-flex items-center gap-2 rounded-lg bg-bambu-dark px-3 py-2 text-sm text-white disabled:opacity-50">{uploading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}{de ? 'Datei auswählen' : 'Choose file'}</button>
        <input ref={fileInput} type="file" accept=".3mf,model/3mf" className="sr-only" onChange={(event) => void upload(event.target.files?.[0])} />
      </div>
      {files.map((file) => <div key={file.id} className="space-y-2"><div className="flex items-center justify-between text-sm"><strong className="text-white">{file.original_filename}</strong><span className="text-bambu-gray">Revision {file.revision_number} · {file.plates.length} {de ? 'Platten' : 'plates'}</span></div><ProjectPlateGrid plates={file.plates} selectedIds={selectedIds} focusedId={focusedId} locale={locale} onSelectionChange={select} onFocusChange={setFocusedId} /></div>)}
      {focusedPlate && focusedSelection && <div className="grid gap-3 rounded-lg border border-bambu-green/30 bg-bambu-dark p-4 sm:grid-cols-2 lg:grid-cols-6">
        <div className="lg:col-span-6 flex items-center justify-between"><strong className="text-white">{focusedPlate.name}</strong><span className="rounded-full bg-bambu-green/10 px-2 py-1 text-xs text-bambu-green">{String(focusedSelection.provenance.source ?? '3mf') === 'estimate' ? (de ? 'Schätzung' : 'Estimate') : String(focusedSelection.provenance.source ?? '3MF/Slicer')}</span></div>
        <label className="text-xs text-bambu-gray">{de ? 'Benötigte Teile' : 'Required parts'}<NumberField min="0" step="1" value={focusedSelection.good_parts} onChange={(event) => updateFocused({ good_parts: Number(event.target.value) })} containerClassName="mt-1" className={inputClass} /></label>
        <label className="text-xs text-bambu-gray">{de ? 'Teile je Druck' : 'Parts per print'}<NumberField min="1" step="1" value={focusedSelection.parts_per_print} onChange={(event) => updateFocused({ parts_per_print: Number(event.target.value) })} containerClassName="mt-1" className={inputClass} /></label>
        <label className="text-xs text-bambu-gray">{de ? 'Ausschussdrucke' : 'Scrap prints'}<NumberField min="0" step="1" value={focusedSelection.scrap_prints} onChange={(event) => updateFocused({ scrap_prints: Number(event.target.value) })} containerClassName="mt-1" className={inputClass} /></label>
        <label className="text-xs text-bambu-gray">{de ? 'Material' : 'Material'}<TextField value={focusedSelection.material_code ?? ''} onChange={(event) => updateFocused({ material_code: event.target.value || null })} className={inputClass} /><span className="mt-1 flex items-center gap-1"><Database className="h-3 w-3" />{de ? 'verfügbar' : 'available'}: {formatGrams(materialAvailable, locale)}</span></label>
        <label className="text-xs text-bambu-gray">{de ? 'g je Druck' : 'g per print'}<NumberField min="0" step="0.1" value={focusedSelection.grams_per_print ?? ''} onChange={(event) => updateFocused({ grams_per_print: event.target.value || null, provenance: { ...focusedSelection.provenance, source: 'manual' } })} containerClassName="mt-1" className={inputClass} /></label>
        <label className="text-xs text-bambu-gray">{de ? 'h je Druck' : 'h per print'}<NumberField min="0" step="0.01" value={focusedSelection.hours_per_print ?? ''} onChange={(event) => updateFocused({ hours_per_print: event.target.value || null, provenance: { ...focusedSelection.provenance, source: 'manual' } })} containerClassName="mt-1" className={inputClass} /></label>
      </div>}
      <div className="flex items-center justify-between gap-3"><span className="text-sm text-bambu-gray">{message}</span><button type="button" disabled={!selectedIds.size || slicing} onClick={() => void slice()} className="inline-flex items-center gap-2 rounded-lg border border-bambu-green px-4 py-2 text-sm text-bambu-green disabled:opacity-50">{slicing ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Database className="h-4 w-4" />}{de ? '3MF slicen & kalkulieren' : 'Slice & calculate 3MF'}</button></div>
    </section>
  );
}

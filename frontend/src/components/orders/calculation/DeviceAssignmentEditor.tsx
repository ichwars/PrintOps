import { Cpu, Wind } from 'lucide-react';
import type { Equipment, Printer } from '../../../api/client';
import type { CalculationOperation } from '../../../api/calculations';
import { NumberField , LegacySelect} from '../../ui';

const inputClass = 'mt-1 h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary px-3 text-white outline-none focus:border-bambu-green';
const numberInputClass = 'h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary px-3 text-white outline-none focus:border-bambu-green';

export function DeviceAssignmentEditor({ operation, printers, dryers, defaultPrinterId, defaultDryerId, locale, onChange }: { operation: CalculationOperation; printers: Printer[]; dryers: Equipment[]; defaultPrinterId: number; defaultDryerId: number; locale: string; onChange: (operation: CalculationOperation) => void }) {
  const de = locale.startsWith('de');
  const printerId = Number(Object.hasOwn(operation.provenance, 'printer_id') ? operation.provenance.printer_id ?? 0 : defaultPrinterId ?? 0);
  const dryerId = Number(Object.hasOwn(operation.provenance, 'dryer_id') ? operation.provenance.dryer_id ?? 0 : defaultDryerId ?? 0);
  const dryingHours = Number(operation.provenance.drying_hours ?? 0);
  const assignPrinter = (id: number) => { const device = printers.find(item => item.id === id); onChange({ ...operation, provenance: { ...operation.provenance, printer_id: id || null, printer_name: device?.name ?? null, printer_hourly_rate: device?.hourly_rate ?? null, printer_power_watts: device?.nominal_power_watts ?? null } }); };
  const assignDryer = (id: number) => { const device = dryers.find(item => item.id === id); onChange({ ...operation, provenance: { ...operation.provenance, dryer_id: id || null, dryer_name: device?.name ?? null, dryer_hourly_rate: device?.hourly_rate ?? null, dryer_power_watts: device?.nominal_power_watts ?? null } }); };
  return <div className="grid gap-3 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary/50 p-3 sm:grid-cols-3 lg:col-span-7"><label className="text-xs text-bambu-gray"><span className="flex items-center gap-1"><Cpu className="h-3.5 w-3.5" />{de ? 'Drucker' : 'Printer'}</span><LegacySelect value={printerId} onChange={e => assignPrinter(Number(e.target.value))} className={inputClass}><option value={0}>{de ? 'Kein Drucker' : 'No printer'}</option>{printers.filter(item => item.is_active).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</LegacySelect></label><label className="text-xs text-bambu-gray"><span className="flex items-center gap-1"><Wind className="h-3.5 w-3.5" />{de ? 'Trockner' : 'Dryer'}</span><LegacySelect value={dryerId} onChange={e => assignDryer(Number(e.target.value))} className={inputClass}><option value={0}>{de ? 'Kein Trockner' : 'No dryer'}</option>{dryers.filter(item => item.is_active).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</LegacySelect></label><label className="text-xs text-bambu-gray">{de ? 'Trocknungsdauer h' : 'Drying hours'}<NumberField min="0" step="0.05" value={dryingHours} onChange={e => onChange({ ...operation, provenance: { ...operation.provenance, drying_hours: Number(e.target.value) } })} containerClassName="mt-1" className={numberInputClass} /></label></div>;
}

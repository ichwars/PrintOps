import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock3, PackageSearch } from 'lucide-react';

import { calculationsApi, type AvailabilityReport, type CalculationVariant } from '../../../api/calculations';
import { formatCount, formatGrams } from '../../../utils/calculationFormatting';

interface Props {
  calculationId: number | null;
  variant: CalculationVariant;
  locale: string;
}

export function AvailabilityPanel({ calculationId, variant, locale }: Props) {
  const de = locale.startsWith('de');
  const [report, setReport] = useState<AvailabilityReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const request = calculationId ? calculationsApi.availability(calculationId) : calculationsApi.availabilityPreview(variant);
      void request.then((result) => { setReport(result); setError(null); }).catch((reason) => { setReport(null); setError(reason instanceof Error ? reason.message : String(reason)); });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [calculationId, variant]);
  const amount = (value: string, unit: string) => unit === 'GRM' ? formatGrams(value, locale) : `${formatCount(value, locale)} ${unit}`;
  return <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark p-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="flex items-center gap-2 font-semibold text-white"><PackageSearch className="h-4 w-4 text-bambu-green" />{de ? 'Lagerverfügbarkeit' : 'Stock availability'}</h3><p className="text-xs text-bambu-gray">{de ? 'Filament und Kleinteile für die aktive Variante.' : 'Filament and small parts for the active variant.'}</p></div><span className="rounded-full bg-bambu-dark-secondary px-3 py-1 text-xs text-bambu-gray">{de ? 'Prüfung ohne Reservierung' : 'Check without reservation'}</span></div>
    {error && <p className="mt-3 text-sm text-amber-200">{error}</p>}
    {!report && !error && <p className="mt-3 text-sm text-bambu-gray">{de ? 'Bestand wird geprüft …' : 'Checking stock …'}</p>}
    {report && <div className="mt-3 space-y-2">{report.lines.length === 0 ? <p className="text-sm text-bambu-gray">{de ? 'Noch keine reservierbaren Bedarfe.' : 'No reservable requirements yet.'}</p> : report.lines.map((line) => <div key={line.source_key} className={`rounded-lg border p-3 ${line.status === 'available' ? 'border-bambu-green/30' : 'border-amber-500/40'}`}><div className="flex items-center justify-between gap-3"><strong className="flex items-center gap-2 text-sm text-white">{line.status === 'available' ? <CheckCircle2 className="h-4 w-4 text-bambu-green" /> : <AlertTriangle className="h-4 w-4 text-amber-300" />}{line.description ?? line.material_code ?? line.source_key}</strong><span className={line.status === 'available' ? 'text-xs text-bambu-green' : 'text-xs text-amber-200'}>{line.status === 'available' ? (de ? 'verfügbar' : 'available') : line.status === 'short' ? (de ? 'zu wenig Bestand' : 'short') : (de ? 'nicht zugeordnet' : 'unmapped')}</span></div><div className="mt-2 grid gap-2 text-xs text-bambu-gray sm:grid-cols-4"><span>{de ? 'Bestand' : 'Physical'} {amount(line.physical, line.unit_code)}</span><span>{de ? 'Reserviert' : 'Reserved'} {amount(line.reserved, line.unit_code)}</span><span>{de ? 'Verfügbar' : 'Available'} {amount(line.available, line.unit_code)}</span><span>{de ? 'Bedarf' : 'Required'} {amount(line.required, line.unit_code)}</span></div></div>)}</div>}
    {report && <p className="mt-3 flex items-center gap-1 text-[11px] text-bambu-gray"><Clock3 className="h-3 w-3" />{de ? 'Zuletzt geprüft' : 'Last checked'}: {new Date(report.checked_at).toLocaleString(locale)}</p>}
  </section>;
}

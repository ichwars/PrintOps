import { Archive, ChevronRight } from 'lucide-react';
import type { CalculationDetail } from '../../api/calculations';

interface Props {
  items: CalculationDetail[];
  locale: string;
  onOpen: (item: CalculationDetail) => void;
}

const STATUS_DE: Record<string, string> = { draft: 'Entwurf', approved: 'Freigegeben', superseded: 'Ersetzt', archived: 'Archiviert' };
const STATUS_EN: Record<string, string> = { draft: 'Draft', approved: 'Approved', superseded: 'Superseded', archived: 'Archived' };

export function CalculationList({ items, locale, onOpen }: Props) {
  const de = locale.startsWith('de');
  const status = de ? STATUS_DE : STATUS_EN;
  const date = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' });
  const money = (value: string | null, currency: string) => value === null ? '—' : new Intl.NumberFormat(locale, { style: 'currency', currency }).format(Number(value));
  return (
    <div className="overflow-x-auto rounded-lg border border-bambu-dark-tertiary">
      <table className="w-full min-w-[1050px] text-sm">
        <thead className="bg-bambu-dark">
          <tr className="text-left text-xs uppercase tracking-wide text-bambu-gray">
            {[de ? 'Kalkulation' : 'Calculation', de ? 'Kunde' : 'Customer', de ? 'Variante' : 'Variant', de ? 'Revision' : 'Revision', de ? 'Status' : 'Status', de ? 'Selbstkosten' : 'Cost', de ? 'Verkaufspreis' : 'Selling price', de ? 'Aktualisiert' : 'Updated', ''].map(label => <th key={label} className="px-4 py-3 font-medium">{label}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-bambu-dark-tertiary">
          {items.map(item => {
            const preferred = item.variants.find(variant => variant.is_preferred);
            return (
              <tr key={item.id} className="bg-bambu-dark-secondary hover:bg-bambu-dark-tertiary/40">
                <td className="px-4 py-3"><div className="font-medium text-white">K-{String(item.id).padStart(6, '0')}</div><div className="text-xs text-bambu-gray">{item.title}</div></td>
                <td className="px-4 py-3 text-bambu-gray">{item.customer_id ? `#${item.customer_id}` : de ? 'Ohne Kundenzuordnung' : 'No customer assigned'}</td>
                <td className="px-4 py-3 text-white">{preferred?.name ?? '—'}</td>
                <td className="px-4 py-3 text-bambu-gray">{item.current_revision ? `R${item.current_revision}` : '—'}</td>
                <td className="px-4 py-3"><span className="inline-flex items-center gap-1 rounded-full bg-bambu-dark px-2 py-1 text-xs text-bambu-green">{item.status === 'archived' && <Archive className="h-3 w-3" />}{status[item.status]}</span></td>
                <td className="px-4 py-3 text-bambu-gray">{money(item.production_cost, item.currency)}</td><td className="px-4 py-3 font-medium text-white">{money(item.selling_price, item.currency)}</td>
                <td className="px-4 py-3 text-bambu-gray">{date.format(new Date(item.updated_at))}</td>
                <td className="px-4 py-3 text-right"><button type="button" onClick={() => onOpen(item)} aria-label={de ? 'Kalkulation öffnen' : 'Open calculation'} className="rounded p-2 text-bambu-gray hover:bg-bambu-dark hover:text-white"><ChevronRight className="h-4 w-4" /></button></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

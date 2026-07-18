import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, Boxes, CircleX, PackageCheck, Scale } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ordersApi, type CustomerOrder } from '../api/offers';
import { NumberField } from '../components/ui';
import { formatCount, formatGrams } from '../utils/calculationFormatting';

export function OrderDetailPage() {
  const { id } = useParams();
  const { i18n } = useTranslation();
  const de = i18n.resolvedLanguage?.startsWith('de') ?? false;
  const locale = de ? 'de-DE' : 'en-US';
  const [order, setOrder] = useState<CustomerOrder | null>(null);
  const [values, setValues] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => { if (!id) return; try { setOrder(await ordersApi.get(Number(id))); setError(null); } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); } }, [id]);
  useEffect(() => { void load(); }, [load]);
  const command = async (kind: 'issue' | 'reconcile', allocationId: number) => {
    if (!order || !values[allocationId]) return;
    try {
      const key = `${kind}-${order.id}-${allocationId}-${Date.now()}`;
      const updated = kind === 'issue' ? await ordersApi.issueSmallPart(order.id, allocationId, values[allocationId], key) : await ordersApi.reconcileFilament(order.id, allocationId, values[allocationId], key);
      setOrder(updated); setValues((current) => ({ ...current, [allocationId]: '' }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  const cancel = async () => {
    if (!order || !window.confirm(de ? 'Auftrag stornieren und alle offenen Reservierungen freigeben?' : 'Cancel order and release all open reservations?')) return;
    try { setOrder(await ordersApi.cancel(order.id, `cancel-${order.id}-${Date.now()}`)); } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  if (!order) return <div className="p-8 text-bambu-gray">{error ?? (de ? 'Auftrag wird geladen …' : 'Loading order …')}</div>;
  return <div className="space-y-5 p-4 md:p-8">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><Link to="/orders/offers" className="mb-3 inline-flex items-center gap-1 text-sm text-bambu-gray hover:text-white"><ArrowLeft className="h-4 w-4" />{de ? 'Zu den Angeboten' : 'Back to offers'}</Link><h1 className="flex items-center gap-3 text-2xl font-bold text-white"><Boxes className="h-7 w-7 text-bambu-green" />{order.number}</h1><p className="mt-1 text-bambu-gray">{de ? 'Auftrag und verbindliche Lagerreservierungen' : 'Order and binding stock reservations'}</p></div><div className="flex items-center gap-3"><Link to={`/projects/${order.project_id}`} className="rounded-lg border border-bambu-green px-4 py-2 text-sm text-bambu-green">{de ? 'Projekt öffnen' : 'Open project'}</Link>{order.status === 'active' && <button onClick={() => void cancel()} className="inline-flex items-center gap-2 rounded-lg border border-red-500/40 px-4 py-2 text-sm text-red-300"><CircleX className="h-4 w-4" />{de ? 'Stornieren' : 'Cancel'}</button>}</div></div>
    {error && <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-red-200">{error}</div>}
    <div className="grid gap-3 sm:grid-cols-3"><div className="rounded-lg bg-bambu-dark p-4"><span className="text-xs text-bambu-gray">Status</span><strong className="mt-1 block text-white">{order.status}</strong></div><div className="rounded-lg bg-bambu-dark p-4"><span className="text-xs text-bambu-gray">{de ? 'Angebot' : 'Offer'}</span><strong className="mt-1 block text-white">#{order.offer_id}</strong></div><div className="rounded-lg bg-bambu-dark p-4"><span className="text-xs text-bambu-gray">{de ? 'Projekt' : 'Project'}</span><strong className="mt-1 block text-white">#{order.project_id}</strong></div></div>
    <section><h2 className="mb-3 font-semibold text-white">{de ? 'Reservierungen' : 'Reservations'}</h2><div className="space-y-3">{order.reservations.map((reservation) => <article key={reservation.id} className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark p-4"><div className="flex items-center justify-between"><div><strong className="text-white">{reservation.resource_kind === 'filament' ? reservation.material_code : reservation.source_key}</strong><span className="ml-2 text-xs text-bambu-gray">{reservation.resource_kind === 'filament' ? formatGrams(reservation.requested_quantity, locale) : `${formatCount(reservation.requested_quantity, locale)} ${reservation.unit_code}`}</span></div><span className="rounded-full bg-bambu-dark-secondary px-2 py-1 text-xs text-bambu-gray">{reservation.status}</span></div><div className="mt-3 space-y-2">{reservation.allocations.map((allocation) => {
        const remaining = Number(allocation.allocated_quantity) - Number(allocation.consumed_quantity);
        return <div key={allocation.id} className="grid items-center gap-3 rounded-lg bg-bambu-dark-secondary p-3 md:grid-cols-[1fr_160px_130px_auto]"><div className="text-sm text-white">{allocation.small_part_id ? `${de ? 'Kleinteil' : 'Small part'} #${allocation.small_part_id}` : `${de ? 'Spule' : 'Spool'} #${allocation.spool_id ?? allocation.external_spool_id}`}</div><div className="text-xs text-bambu-gray">{de ? 'Offen' : 'Remaining'}: {reservation.resource_kind === 'filament' ? formatGrams(remaining, locale) : `${formatCount(remaining, locale)} ${reservation.unit_code}`}</div>{order.status === 'active' && reservation.status === 'active' && <NumberField aria-label={de ? 'Menge' : 'Quantity'} min="0.001" step={reservation.resource_kind === 'filament' ? '0.1' : '1'} value={values[allocation.id] ?? ''} onValueChange={(value) => setValues((current) => ({ ...current, [allocation.id]: value }))} placeholder={de ? 'Menge' : 'Quantity'} className="h-9 rounded border border-bambu-dark-tertiary bg-bambu-dark px-3 text-white" />}{order.status === 'active' && reservation.status === 'active' && <button disabled={!values[allocation.id]} onClick={() => void command(reservation.resource_kind === 'small_part' ? 'issue' : 'reconcile', allocation.id)} className="inline-flex items-center gap-2 rounded-lg border border-bambu-green px-3 py-2 text-xs text-bambu-green disabled:opacity-40">{reservation.resource_kind === 'small_part' ? <PackageCheck className="h-4 w-4" /> : <Scale className="h-4 w-4" />}{reservation.resource_kind === 'small_part' ? (de ? 'Ausgeben' : 'Issue') : (de ? 'Verbrauch buchen' : 'Reconcile')}</button>}</div>;
      })}</div></article>)}</div></section>
  </div>;
}

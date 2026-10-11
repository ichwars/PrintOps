import { useCallback, useEffect, useState } from 'react';
import { Check, FileText, RefreshCw, Send, XCircle } from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { offersApi, type Offer, type OfferStatus } from '../api/offers';
import { Select } from '../components/ui';
import { formatMoney } from '../utils/calculationFormatting';

function snapshotPart(offer: Offer, key: string): Record<string, unknown> {
  const value = offer.snapshot[key];
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function OffersPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? i18n.language ?? 'en';
  const [offers, setOffers] = useState<Offer[]>([]);
  const [filter, setFilter] = useState<OfferStatus | ''>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => { setLoading(true); try { setOffers(await offersApi.list(filter || undefined)); setError(null); } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); } finally { setLoading(false); } }, [filter]);
  useEffect(() => { void load(); }, [load]);
  const action = async (offer: Offer, kind: 'send' | 'reject' | 'accept') => {
    if (kind === 'accept' && !window.confirm(t('orders.runtimeCalculation.acceptOfferAndReserveStock', { lng: locale }))) return;
    try {
      if (kind === 'send') await offersApi.send(offer.id, offer.version);
      else if (kind === 'reject') await offersApi.reject(offer.id, offer.version);
      else await offersApi.accept(offer.id, offer.version, `accept-${offer.id}-${Date.now()}`);
      await load();
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === 'reservation_blocked') setError(t('orders.runtimeCalculation.reservationBlocked', { lng: locale, message: reason.message }));
      else setError(reason instanceof Error ? reason.message : String(reason));
    }
  };
  const statusLabel = (status: OfferStatus) => ({ draft: t('settings.documentLayout.statuses.draft', { lng: locale }), sent: t('orders.runtimeCalculation.sent', { lng: locale }), accepted: t('orders.runtimeCalculation.accepted', { lng: locale }), rejected: t('orders.runtimeCalculation.rejected', { lng: locale }) })[status];
  return <div className="space-y-5 p-4 md:p-8">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="flex items-center gap-3 text-2xl font-bold text-white"><FileText className="h-7 w-7 text-bambu-green" />{t('printops.nav.offers', { lng: locale })}</h1><p className="mt-1 text-bambu-gray">{t('orders.runtimeCalculation.draftSendAndAcceptWithBindingStockReservation', { lng: locale })}</p></div><Select ariaLabel={t('orders.runtimeCalculation.filterOfferStatus', { lng: locale })} value={filter} onValueChange={(value) => setFilter(value)} options={[{ value: '', label: t('printers.filter.allStatuses', { lng: locale }) }, { value: 'draft', label: t('settings.documentLayout.statuses.draft', { lng: locale }) }, { value: 'sent', label: t('orders.runtimeCalculation.sent', { lng: locale }) }, { value: 'accepted', label: t('orders.runtimeCalculation.accepted', { lng: locale }) }, { value: 'rejected', label: t('orders.runtimeCalculation.rejected', { lng: locale }) }]} controlClassName="h-10 min-w-44" /></div>
    {error && <div className="flex items-center justify-between rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-red-200"><span>{error}</span><button onClick={() => void load()}><RefreshCw className="h-4 w-4" /></button></div>}
    <div className="overflow-x-auto rounded-xl border border-bambu-dark-tertiary"><table className="w-full text-sm"><thead className="bg-bambu-dark"><tr>{[t('orders.runtimeCalculation.offer', { lng: locale }), t('printops.nav.calculation', { lng: locale }), t('orders.customers.customer', { lng: locale }), t('orders.runtimeCalculation.revisionLabel', { lng: locale }), t('inventory.net', { lng: locale }), t('common.status', { lng: locale }), t('orders.runtimeCalculation.updatedOffersPage', { lng: locale }), t('common.actions', { lng: locale })].map((item) => <th key={item} className="px-4 py-3 text-left font-medium text-bambu-gray">{item}</th>)}</tr></thead><tbody className="divide-y divide-bambu-dark-tertiary">{loading ? <tr><td colSpan={8} className="px-4 py-10 text-center text-bambu-gray">{t('orders.runtimeCalculation.loadingOffers', { lng: locale })}</td></tr> : offers.length === 0 ? <tr><td colSpan={8} className="px-4 py-10 text-center text-bambu-gray">{t('orders.runtimeCalculation.noOffersYet', { lng: locale })}</td></tr> : offers.map((offer) => {
      const calculation = snapshotPart(offer, 'calculation'); const revision = snapshotPart(offer, 'revision'); const currency = String(revision.currency ?? calculation.currency ?? 'EUR');
      return <tr key={offer.id} className="bg-bambu-dark-secondary"><td className="px-4 py-3 font-medium text-white"><div>{offer.number}</div>{offer.quotation_document_id ? <div className="mt-1 text-xs font-normal text-bambu-gray">{t('orders.runtimeCalculation.document', { lng: locale })} #{offer.quotation_document_id}</div> : null}</td><td className="px-4 py-3 text-white">{String(calculation.title ?? `K-${calculation.id ?? ''}`)}</td><td className="px-4 py-3 text-bambu-gray">{offer.customer_id ? `#${offer.customer_id}` : (t('orders.runtimeCalculation.noCustomerOffersPage', { lng: locale }))}</td><td className="px-4 py-3 text-bambu-gray">{String(revision.revision_number ?? '–')}</td><td className="px-4 py-3 text-white">{formatMoney(String(revision.selling_price ?? 0), locale, currency)}</td><td className="px-4 py-3"><span className={`rounded-full px-2 py-1 text-xs ${offer.status === 'accepted' ? 'bg-bambu-green/10 text-bambu-green' : offer.status === 'rejected' ? 'bg-red-500/10 text-red-300' : 'bg-bambu-dark text-bambu-gray'}`}>{statusLabel(offer.status)}</span></td><td className="px-4 py-3 text-bambu-gray">{new Date(offer.updated_at).toLocaleString(locale)}</td><td className="px-4 py-3"><div className="flex gap-2">{offer.status === 'draft' && <button aria-label={t('orders.runtimeCalculation.sendOffer', { lng: locale })} onClick={() => void action(offer, 'send')} className="rounded p-2 text-bambu-green"><Send className="h-4 w-4" /></button>}{offer.status === 'sent' && <><button aria-label={t('orders.runtimeCalculation.acceptOffer', { lng: locale })} onClick={() => void action(offer, 'accept')} className="rounded p-2 text-bambu-green"><Check className="h-4 w-4" /></button><button aria-label={t('orders.runtimeCalculation.rejectOffer', { lng: locale })} onClick={() => void action(offer, 'reject')} className="rounded p-2 text-red-300"><XCircle className="h-4 w-4" /></button></>}{offer.order_id && <Link to={`/orders/${offer.order_id}`} className="rounded bg-bambu-green/10 px-3 py-2 text-xs text-bambu-green">{t('orders.runtimeCalculation.order', { lng: locale })}</Link>}</div></td></tr>;
    })}</tbody></table></div>
  </div>;
}

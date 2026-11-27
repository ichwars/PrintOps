import { useCallback, useEffect, useMemo, useState } from 'react';
import { Check, FileText, RefreshCw, Search, Send, X, XCircle } from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { offersApi, type Offer, type OfferStatus } from '../api/offers';
import { Button, Select, TextField } from '../components/ui';
import { ConfirmModal } from '../components/ConfirmModal';
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
  const [searchInput, setSearchInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [acceptTarget, setAcceptTarget] = useState<Offer | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const load = useCallback(async () => { setLoading(true); try { setOffers(await offersApi.list(filter || undefined)); setError(null); } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); } finally { setLoading(false); } }, [filter]);
  useEffect(() => { void load(); }, [load]);
  const action = async (offer: Offer, kind: 'send' | 'reject' | 'accept') => {
    try {
      setActionPending(true);
      if (kind === 'send') await offersApi.send(offer.id, offer.version);
      else if (kind === 'reject') await offersApi.reject(offer.id, offer.version);
      else await offersApi.accept(offer.id, offer.version, `accept-${offer.id}-${Date.now()}`);
      await load();
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === 'reservation_blocked') setError(t('orders.runtimeCalculation.reservationBlocked', { lng: locale, message: reason.message }));
      else setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setActionPending(false);
    }
  };
  const confirmAccept = async () => {
    if (!acceptTarget) return;
    await action(acceptTarget, 'accept');
    setAcceptTarget(null);
  };
  const filteredOffers = useMemo(() => {
    const needle = searchInput.trim().toLowerCase();
    if (!needle) return offers;
    return offers.filter((offer) => {
      const calculation = snapshotPart(offer, 'calculation');
      const candidates = [
        offer.number,
        String(calculation.title ?? ''),
        offer.customer_id != null ? `#${offer.customer_id}` : '',
      ];
      return candidates.some((value) => value.toLowerCase().includes(needle));
    });
  }, [offers, searchInput]);
  const statusLabel = (status: OfferStatus) => ({ draft: t('settings.documentLayout.statuses.draft', { lng: locale }), sent: t('orders.runtimeCalculation.sent', { lng: locale }), accepted: t('orders.runtimeCalculation.accepted', { lng: locale }), rejected: t('orders.runtimeCalculation.rejected', { lng: locale }) })[status];
  return <div className="space-y-5 p-4 md:p-8">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="flex items-center gap-3 text-2xl font-bold text-white"><FileText className="h-7 w-7 text-bambu-green" />{t('printops.nav.offers', { lng: locale })}</h1><p className="mt-1 text-bambu-gray">{t('orders.runtimeCalculation.draftSendAndAcceptWithBindingStockReservation', { lng: locale })}</p></div><div className="flex flex-wrap items-center gap-3"><div className="relative w-full max-w-xs"><Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-bambu-gray/50" /><TextField type="search" aria-label={t('orders.runtimeCalculation.searchOffers', { lng: locale })} value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder={t('orders.runtimeCalculation.searchOffersPlaceholder', { lng: locale })} className={`w-full pl-9 ${searchInput ? 'pr-8' : ''}`} />{searchInput ? <button type="button" onClick={() => setSearchInput('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-bambu-gray hover:text-white" aria-label={t('orders.runtimeCalculation.clearSearch', { lng: locale })}><X aria-hidden="true" className="h-4 w-4" /></button> : null}</div><Select ariaLabel={t('orders.runtimeCalculation.filterOfferStatus', { lng: locale })} value={filter} onValueChange={(value) => setFilter(value)} options={[{ value: '', label: t('printers.filter.allStatuses', { lng: locale }) }, { value: 'draft', label: t('settings.documentLayout.statuses.draft', { lng: locale }) }, { value: 'sent', label: t('orders.runtimeCalculation.sent', { lng: locale }) }, { value: 'accepted', label: t('orders.runtimeCalculation.accepted', { lng: locale }) }, { value: 'rejected', label: t('orders.runtimeCalculation.rejected', { lng: locale }) }]} controlClassName="h-10 min-w-44" /></div></div>
    {error && <div className="flex items-center justify-between rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-red-200"><span>{error}</span><button onClick={() => void load()}><RefreshCw className="h-4 w-4" /></button></div>}
    <div className="overflow-x-auto rounded-xl border border-bambu-dark-tertiary"><table className="w-full text-sm"><thead className="bg-bambu-dark"><tr>{[t('orders.runtimeCalculation.offer', { lng: locale }), t('printops.nav.calculation', { lng: locale }), t('orders.customers.customer', { lng: locale }), t('orders.runtimeCalculation.revisionLabel', { lng: locale }), t('inventory.net', { lng: locale }), t('common.status', { lng: locale }), t('orders.runtimeCalculation.updatedOffersPage', { lng: locale }), t('common.actions', { lng: locale })].map((item) => <th key={item} className="px-4 py-3 text-left font-medium text-bambu-gray">{item}</th>)}</tr></thead><tbody className="divide-y divide-bambu-dark-tertiary">{loading ? <tr><td colSpan={8} className="px-4 py-10 text-center text-bambu-gray">{t('orders.runtimeCalculation.loadingOffers', { lng: locale })}</td></tr> : offers.length === 0 ? <tr><td colSpan={8} className="px-4 py-10 text-center text-bambu-gray">{t('orders.runtimeCalculation.noOffersYet', { lng: locale })}</td></tr> : filteredOffers.length === 0 ? <tr><td colSpan={8} className="px-4 py-10 text-center text-bambu-gray">{t('orders.runtimeCalculation.noOffersMatchSearch', { lng: locale })}</td></tr> : filteredOffers.map((offer) => {
      const calculation = snapshotPart(offer, 'calculation'); const revision = snapshotPart(offer, 'revision'); const currency = String(revision.currency ?? calculation.currency ?? 'EUR');
      return <tr key={offer.id} className="bg-bambu-dark-secondary"><td className="px-4 py-3 font-medium text-white"><div>{offer.number}</div>{offer.quotation_document_id ? <div className="mt-1 text-xs font-normal text-bambu-gray">{t('orders.runtimeCalculation.document', { lng: locale })} #{offer.quotation_document_id}</div> : null}</td><td className="px-4 py-3 text-white">{String(calculation.title ?? `K-${calculation.id ?? ''}`)}</td><td className="px-4 py-3 text-bambu-gray">{offer.customer_id ? `#${offer.customer_id}` : (t('orders.runtimeCalculation.noCustomerOffersPage', { lng: locale }))}</td><td className="px-4 py-3 text-bambu-gray">{String(revision.revision_number ?? '–')}</td><td className="px-4 py-3 text-white">{formatMoney(String(revision.selling_price ?? 0), locale, currency)}</td><td className="px-4 py-3"><span className={`rounded-full px-2 py-1 text-xs ${offer.status === 'accepted' ? 'bg-bambu-green/10 text-bambu-green' : offer.status === 'rejected' ? 'bg-red-500/10 text-red-300' : 'bg-bambu-dark text-bambu-gray'}`}>{statusLabel(offer.status)}</span></td><td className="px-4 py-3 text-bambu-gray">{new Date(offer.updated_at).toLocaleString(locale)}</td><td className="px-4 py-3"><div className="flex flex-wrap gap-2">{offer.status === 'draft' && <Button type="button" size="sm" variant="secondary" onClick={() => void action(offer, 'send')}><Send aria-hidden="true" className="h-4 w-4" />{t('orders.runtimeCalculation.sendOffer', { lng: locale })}</Button>}{offer.status === 'sent' && <><Button type="button" size="sm" variant="secondary" onClick={() => setAcceptTarget(offer)}><Check aria-hidden="true" className="h-4 w-4" />{t('orders.runtimeCalculation.acceptOffer', { lng: locale })}</Button><Button type="button" size="sm" variant="secondary" onClick={() => void action(offer, 'reject')}><XCircle aria-hidden="true" className="h-4 w-4" />{t('orders.runtimeCalculation.rejectOffer', { lng: locale })}</Button></>}{offer.order_id && <Link to={`/orders/${offer.order_id}`} className="rounded bg-bambu-green/10 px-3 py-2 text-xs text-bambu-green">{t('orders.runtimeCalculation.order', { lng: locale })}</Link>}</div></td></tr>;
    })}</tbody></table></div>
    {acceptTarget && <ConfirmModal variant="warning" title={t('orders.runtimeCalculation.acceptOfferConfirmTitle', { lng: locale })} message={t('orders.runtimeCalculation.acceptOfferAndReserveStock', { lng: locale })} confirmText={t('orders.runtimeCalculation.acceptOffer', { lng: locale })} isLoading={actionPending} onConfirm={() => void confirmAccept()} onCancel={() => setAcceptTarget(null)} />}
  </div>;
}

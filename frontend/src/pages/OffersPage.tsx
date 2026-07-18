import { useCallback, useEffect, useState } from 'react';
import { Check, FileText, RefreshCw, Send, XCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { offersApi, type Offer, type OfferStatus } from '../api/offers';
import { formatMoney } from '../utils/calculationFormatting';

function snapshotPart(offer: Offer, key: string): Record<string, unknown> {
  const value = offer.snapshot[key];
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function OffersPage() {
  const { i18n } = useTranslation();
  const de = i18n.resolvedLanguage?.startsWith('de') ?? false;
  const locale = de ? 'de-DE' : 'en-US';
  const [offers, setOffers] = useState<Offer[]>([]);
  const [filter, setFilter] = useState<OfferStatus | ''>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => { setLoading(true); try { setOffers(await offersApi.list(filter || undefined)); setError(null); } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); } finally { setLoading(false); } }, [filter]);
  useEffect(() => { void load(); }, [load]);
  const action = async (offer: Offer, kind: 'send' | 'reject' | 'accept') => {
    if (kind === 'accept' && !window.confirm(de ? 'Angebot annehmen und Lager verbindlich reservieren?' : 'Accept offer and reserve stock?')) return;
    try {
      if (kind === 'send') await offersApi.send(offer.id, offer.version);
      else if (kind === 'reject') await offersApi.reject(offer.id, offer.version);
      else await offersApi.accept(offer.id, offer.version, `accept-${offer.id}-${Date.now()}`);
      await load();
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === 'reservation_blocked') setError(de ? `Reservierung blockiert: ${reason.message}` : `Reservation blocked: ${reason.message}`);
      else setError(reason instanceof Error ? reason.message : String(reason));
    }
  };
  const statusLabel = (status: OfferStatus) => ({ draft: de ? 'Entwurf' : 'Draft', sent: de ? 'Versendet' : 'Sent', accepted: de ? 'Angenommen' : 'Accepted', rejected: de ? 'Abgelehnt' : 'Rejected' })[status];
  return <div className="space-y-5 p-4 md:p-8">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="flex items-center gap-3 text-2xl font-bold text-white"><FileText className="h-7 w-7 text-bambu-green" />{de ? 'Angebote' : 'Offers'}</h1><p className="mt-1 text-bambu-gray">{de ? 'Entwurf, Versand und Annahme mit verbindlicher Lagerreservierung.' : 'Draft, send, and accept with binding stock reservation.'}</p></div><select value={filter} onChange={(event) => setFilter(event.target.value as OfferStatus | '')} className="h-10 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-white"><option value="">{de ? 'Alle Status' : 'All statuses'}</option><option value="draft">{de ? 'Entwurf' : 'Draft'}</option><option value="sent">{de ? 'Versendet' : 'Sent'}</option><option value="accepted">{de ? 'Angenommen' : 'Accepted'}</option><option value="rejected">{de ? 'Abgelehnt' : 'Rejected'}</option></select></div>
    {error && <div className="flex items-center justify-between rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-red-200"><span>{error}</span><button onClick={() => void load()}><RefreshCw className="h-4 w-4" /></button></div>}
    <div className="overflow-x-auto rounded-xl border border-bambu-dark-tertiary"><table className="w-full text-sm"><thead className="bg-bambu-dark"><tr>{[de ? 'Angebot' : 'Offer', de ? 'Kalkulation' : 'Calculation', de ? 'Kunde' : 'Customer', 'Revision', de ? 'Netto' : 'Net', 'Status', de ? 'Aktualisiert' : 'Updated', de ? 'Aktionen' : 'Actions'].map((item) => <th key={item} className="px-4 py-3 text-left font-medium text-bambu-gray">{item}</th>)}</tr></thead><tbody className="divide-y divide-bambu-dark-tertiary">{loading ? <tr><td colSpan={8} className="px-4 py-10 text-center text-bambu-gray">{de ? 'Angebote werden geladen …' : 'Loading offers …'}</td></tr> : offers.length === 0 ? <tr><td colSpan={8} className="px-4 py-10 text-center text-bambu-gray">{de ? 'Noch keine Angebote.' : 'No offers yet.'}</td></tr> : offers.map((offer) => {
      const calculation = snapshotPart(offer, 'calculation'); const revision = snapshotPart(offer, 'revision'); const currency = String(revision.currency ?? calculation.currency ?? 'EUR');
      return <tr key={offer.id} className="bg-bambu-dark-secondary"><td className="px-4 py-3 font-medium text-white">{offer.number}</td><td className="px-4 py-3 text-white">{String(calculation.title ?? `K-${calculation.id ?? ''}`)}</td><td className="px-4 py-3 text-bambu-gray">{offer.customer_id ? `#${offer.customer_id}` : (de ? 'Ohne Kunde' : 'No customer')}</td><td className="px-4 py-3 text-bambu-gray">{String(revision.revision_number ?? '–')}</td><td className="px-4 py-3 text-white">{formatMoney(String(revision.selling_price ?? 0), locale, currency)}</td><td className="px-4 py-3"><span className={`rounded-full px-2 py-1 text-xs ${offer.status === 'accepted' ? 'bg-bambu-green/10 text-bambu-green' : offer.status === 'rejected' ? 'bg-red-500/10 text-red-300' : 'bg-bambu-dark text-bambu-gray'}`}>{statusLabel(offer.status)}</span></td><td className="px-4 py-3 text-bambu-gray">{new Date(offer.updated_at).toLocaleString(locale)}</td><td className="px-4 py-3"><div className="flex gap-2">{offer.status === 'draft' && <button aria-label={de ? 'Angebot versenden' : 'Send offer'} onClick={() => void action(offer, 'send')} className="rounded p-2 text-bambu-green"><Send className="h-4 w-4" /></button>}{offer.status === 'sent' && <><button aria-label={de ? 'Angebot annehmen' : 'Accept offer'} onClick={() => void action(offer, 'accept')} className="rounded p-2 text-bambu-green"><Check className="h-4 w-4" /></button><button aria-label={de ? 'Angebot ablehnen' : 'Reject offer'} onClick={() => void action(offer, 'reject')} className="rounded p-2 text-red-300"><XCircle className="h-4 w-4" /></button></>}{offer.order_id && <Link to={`/orders/${offer.order_id}`} className="rounded bg-bambu-green/10 px-3 py-2 text-xs text-bambu-green">{de ? 'Auftrag' : 'Order'}</Link>}</div></td></tr>;
    })}</tbody></table></div>
  </div>;
}

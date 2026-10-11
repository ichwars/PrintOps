import { resolveSupportedLanguage } from '../../../i18n';
import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { FilePlus2, LockKeyhole } from 'lucide-react';

import { offersApi } from '../../../api/offers';

export function FollowUpActions({ locale, calculationRevisionId }: { locale: string; calculationRevisionId: number | null }) {
  const language = resolveSupportedLanguage(locale);
  const { t } = useTranslation(undefined, { lng: language });
  const [message, setMessage] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const create = async () => {
    if (!calculationRevisionId) return;
    setCreating(true); setMessage(null);
    try {
      const offer = await offersApi.create(calculationRevisionId);
      setMessage(`${t('orders.runtimeCalculation.offerDraftCreated', { lng: language })}: ${offer.number}`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
    finally { setCreating(false); }
  };
  return <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark p-4"><h3 className="font-semibold text-white">{t('orders.runtimeCalculation.optionalFollowUpActions', { lng: language })}</h3><div className="mt-3 flex flex-wrap gap-3"><button type="button" aria-label={t('orders.runtimeCalculation.createOfferDraft', { lng: language })} disabled={!calculationRevisionId || creating} onClick={() => void create()} className="inline-flex items-center gap-2 rounded-lg border border-bambu-green px-4 py-2 text-sm text-bambu-green disabled:opacity-40"><FilePlus2 className="h-4 w-4" />{t('orders.runtimeCalculation.createOfferDraft', { lng: language })}</button><button type="button" aria-label={t('orders.runtimeCalculation.createPrintOrder', { lng: language })} disabled className="inline-flex items-center gap-2 rounded-lg border border-bambu-dark-tertiary px-4 py-2 text-sm text-bambu-gray opacity-50"><LockKeyhole className="h-4 w-4" />{t('orders.runtimeCalculation.printOrderAfterAcceptance', { lng: language })}</button></div><p className="mt-2 text-xs text-bambu-gray">{calculationRevisionId ? (t('orders.runtimeCalculation.usesImmutableCalculationRevisionNoReservationYet', { lng: language, calculationRevisionId: calculationRevisionId })) : (t('orders.runtimeCalculation.availableAfterCalculationApproval', { lng: language }))}</p>{message && <p className="mt-2 text-sm text-bambu-green">{message}</p>}</section>;
}

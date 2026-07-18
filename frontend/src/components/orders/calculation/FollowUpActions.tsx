import { useState } from 'react';
import { FilePlus2, LockKeyhole } from 'lucide-react';

import { offersApi } from '../../../api/offers';

export function FollowUpActions({ locale, calculationRevisionId }: { locale: string; calculationRevisionId: number | null }) {
  const de = locale.startsWith('de');
  const [message, setMessage] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const create = async () => {
    if (!calculationRevisionId) return;
    setCreating(true); setMessage(null);
    try {
      const offer = await offersApi.create(calculationRevisionId);
      setMessage(`${de ? 'Angebotsentwurf erstellt' : 'Offer draft created'}: ${offer.number}`);
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
    finally { setCreating(false); }
  };
  return <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark p-4"><h3 className="font-semibold text-white">{de ? 'Optionale Folgeaktionen' : 'Optional follow-up actions'}</h3><div className="mt-3 flex flex-wrap gap-3"><button type="button" aria-label={de ? 'Angebotsentwurf erstellen' : 'Create offer draft'} disabled={!calculationRevisionId || creating} onClick={() => void create()} className="inline-flex items-center gap-2 rounded-lg border border-bambu-green px-4 py-2 text-sm text-bambu-green disabled:opacity-40"><FilePlus2 className="h-4 w-4" />{de ? 'Angebotsentwurf erstellen' : 'Create offer draft'}</button><button type="button" aria-label={de ? 'Druckauftrag erstellen' : 'Create print order'} disabled className="inline-flex items-center gap-2 rounded-lg border border-bambu-dark-tertiary px-4 py-2 text-sm text-bambu-gray opacity-50"><LockKeyhole className="h-4 w-4" />{de ? 'Druckauftrag nach Annahme' : 'Print order after acceptance'}</button></div><p className="mt-2 text-xs text-bambu-gray">{calculationRevisionId ? (de ? `Verwendet die unveränderliche Kalkulationsrevision ${calculationRevisionId}. Noch keine Reservierung.` : `Uses immutable calculation revision ${calculationRevisionId}. No reservation yet.`) : (de ? 'Nach Freigabe der Kalkulation verfügbar.' : 'Available after calculation approval.')}</p>{message && <p className="mt-2 text-sm text-bambu-green">{message}</p>}</section>;
}

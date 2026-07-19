import { useEffect, useId, useState } from 'react';
import { Plus, Star, Trash2 } from 'lucide-react';

import type { ProcurementOfferDraft, Supplier } from '../../api/procurement';
import {
  Button,
  Checkbox,
  NumberField,
  Select,
  TextField,
  type SelectOption,
} from '../ui';

interface ProcurementOffersEditorProps {
  suppliers: Supplier[];
  offers: ProcurementOfferDraft[];
  onChange: (offers: ProcurementOfferDraft[]) => void;
  readOnly?: boolean;
}

type OfferWithSnapshot = ProcurementOfferDraft & { supplier?: Supplier };

const emptyOffer = (isPreferred: boolean): ProcurementOfferDraft => ({
  supplier_id: null,
  supplier_sku: '',
  purchase_url: '',
  package_quantity: '1',
  package_unit_code: 'C62',
  minimum_order_quantity: '1',
  lead_time_days: null,
  net_price: '0',
  gross_price: '0',
  is_preferred: isPreferred,
  is_active: true,
});

const integerOrNull = (value: string): number | null => {
  if (!value.trim()) return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : null;
};

function ensurePreferred(offers: OfferWithSnapshot[]): OfferWithSnapshot[] {
  if (offers.some((offer) => offer.is_active && offer.is_preferred)) return offers;
  const firstActive = offers.findIndex((offer) => offer.is_active);
  if (firstActive < 0) return offers;
  return offers.map((offer, index) => ({ ...offer, is_preferred: index === firstActive }));
}

export function ProcurementOffersEditor({
  suppliers,
  offers,
  onChange,
  readOnly = false,
}: ProcurementOffersEditorProps) {
  const [visibleOffers, setVisibleOffers] = useState<OfferWithSnapshot[]>(offers);

  useEffect(() => setVisibleOffers(offers), [offers]);

  const commit = (next: OfferWithSnapshot[]) => {
    if (readOnly) return;
    setVisibleOffers(next);
    onChange(next);
  };

  const update = <K extends keyof ProcurementOfferDraft>(
    index: number,
    key: K,
    value: ProcurementOfferDraft[K],
  ) => {
    const next = visibleOffers.map((offer, offerIndex) =>
      offerIndex === index ? { ...offer, [key]: value } : offer);
    if (key === 'is_active') {
      const withoutInactivePreferred = next.map((offer, offerIndex) =>
        offerIndex === index && !value ? { ...offer, is_preferred: false } : offer);
      commit(ensurePreferred(withoutInactivePreferred));
      return;
    }
    commit(next);
  };

  const selectSupplier = (index: number, supplierId: number | null) => {
    const selected = suppliers.find((candidate) => candidate.id === supplierId);
    commit(visibleOffers.map((offer, offerIndex) =>
      offerIndex === index
        ? {
            ...offer,
            supplier_id: supplierId,
            lead_time_days: selected?.default_lead_time_days ?? null,
            supplier: selected,
          }
        : offer));
  };

  const promote = (index: number) => {
    commit(visibleOffers.map((offer, offerIndex) => ({
      ...offer,
      is_preferred: offerIndex === index,
    })));
  };

  const removeOrDeactivate = (index: number) => {
    const offer = visibleOffers[index];
    const next = offer.id === undefined
      ? visibleOffers.filter((_, offerIndex) => offerIndex !== index)
      : visibleOffers.map((candidate, offerIndex) =>
          offerIndex === index
            ? { ...candidate, is_active: false, is_preferred: false }
            : candidate);
    commit(ensurePreferred(next));
  };

  const preferredIndex = visibleOffers.findIndex((offer) => offer.is_preferred);
  const alternativeIndex = visibleOffers.findIndex(
    (offer, index) => index !== preferredIndex && offer.is_active,
  );
  const additionalIndices = visibleOffers
    .map((_, index) => index)
    .filter((index) => index !== preferredIndex && index !== alternativeIndex);
  const addOffer = () => commit(ensurePreferred([...visibleOffers, emptyOffer(false)]));

  const section = (index: number, title: string) => (
    <OfferSection
      key={visibleOffers[index].id ?? `new-${index}`}
      title={title}
      offer={visibleOffers[index]}
      offerIndex={index}
      suppliers={suppliers}
      readOnly={readOnly}
      onUpdate={update}
      onSelectSupplier={selectSupplier}
      onPromote={promote}
      onRemove={removeOrDeactivate}
    />
  );

  return (
    <div className="space-y-4">
      {preferredIndex >= 0 ? section(preferredIndex, 'Bevorzugte Bezugsquelle') : null}
      {alternativeIndex >= 0 ? section(alternativeIndex, 'Alternative Bezugsquelle') : null}
      {additionalIndices.length > 0 ? (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-white">Weitere Bezugsquellen</h3>
          {additionalIndices.map((index, position) =>
            section(index, `Weitere Bezugsquelle ${position + 1}`))}
        </div>
      ) : null}
      {!readOnly ? (
        <Button type="button" variant="secondary" onClick={addOffer}>
          <Plus aria-hidden="true" className="h-4 w-4" />
          {visibleOffers.length === 0
            ? 'Bezugsquelle hinzufügen'
            : alternativeIndex < 0
              ? 'Alternative Bezugsquelle hinzufügen'
              : 'Weitere Bezugsquelle hinzufügen'}
        </Button>
      ) : null}
    </div>
  );
}

interface OfferSectionProps {
  title: string;
  offer: OfferWithSnapshot;
  offerIndex: number;
  suppliers: Supplier[];
  readOnly: boolean;
  onUpdate: <K extends keyof ProcurementOfferDraft>(
    index: number,
    key: K,
    value: ProcurementOfferDraft[K],
  ) => void;
  onSelectSupplier: (index: number, supplierId: number | null) => void;
  onPromote: (index: number) => void;
  onRemove: (index: number) => void;
}

function OfferSection({
  title,
  offer,
  offerIndex,
  suppliers,
  readOnly,
  onUpdate,
  onSelectSupplier,
  onPromote,
  onRemove,
}: OfferSectionProps) {
  const headingId = `procurement-offer-${useId().replace(/:/g, '')}`;
  const selectedSupplier = suppliers.find((supplier) => supplier.id === offer.supplier_id)
    ?? (offer.supplier?.id === offer.supplier_id ? offer.supplier : undefined);
  const selectableSuppliers = suppliers.filter(
    (supplier) => supplier.is_active || supplier.id === offer.supplier_id,
  );
  if (selectedSupplier && !selectableSuppliers.some(({ id }) => id === selectedSupplier.id)) {
    selectableSuppliers.push(selectedSupplier);
  }
  const supplierOptions: SelectOption<number | ''>[] = [
    { value: '', label: 'Lieferant auswählen' },
    ...selectableSuppliers.map((supplier) => ({
      value: supplier.id,
      label: supplier.name,
      disabled: !supplier.is_active && supplier.id !== offer.supplier_id,
    })),
  ];

  return (
    <section
      aria-labelledby={headingId}
      className="space-y-4 rounded-xl border border-bambu-dark-tertiary p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 id={headingId} className="text-sm font-semibold text-white">{title}</h3>
          {selectedSupplier && !selectedSupplier.is_active ? (
            <span className="rounded-full bg-bambu-dark-tertiary px-2 py-0.5 text-xs text-bambu-gray-light">
              Lieferant deaktiviert
            </span>
          ) : null}
        </div>
        {!readOnly ? (
          <div className="flex flex-wrap gap-2">
            {!offer.is_preferred && offer.is_active ? (
              <Button type="button" variant="secondary" size="sm" onClick={() => onPromote(offerIndex)}>
                <Star aria-hidden="true" className="h-4 w-4" />
                Als bevorzugt festlegen
              </Button>
            ) : null}
            <Button type="button" variant="ghost" size="sm" onClick={() => onRemove(offerIndex)}>
              <Trash2 aria-hidden="true" className="h-4 w-4 text-red-400" />
              {offer.id === undefined ? 'Entfernen' : 'Deaktivieren'}
            </Button>
          </div>
        ) : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Select
          label="Lieferant"
          required
          value={offer.supplier_id ?? ''}
          options={supplierOptions}
          onValueChange={(value) => onSelectSupplier(
            offerIndex,
            typeof value === 'number' ? value : null,
          )}
          disabled={readOnly}
        />
        <TextField label="Lieferantenartikelnummer" value={offer.supplier_sku ?? ''} onValueChange={(value) => onUpdate(offerIndex, 'supplier_sku', value)} disabled={readOnly} />
        <TextField type="url" label="Bezugs-URL" value={offer.purchase_url ?? ''} onValueChange={(value) => onUpdate(offerIndex, 'purchase_url', value)} disabled={readOnly} className="sm:col-span-2" />
        <NumberField label="Packungsmenge" min={0.000001} step="any" value={offer.package_quantity} onValueChange={(value) => onUpdate(offerIndex, 'package_quantity', value)} disabled={readOnly} />
        <TextField label="Packungseinheit" required value={offer.package_unit_code} onValueChange={(value) => onUpdate(offerIndex, 'package_unit_code', value)} disabled={readOnly} />
        <NumberField label="Mindestbestellmenge" min={0.000001} step="any" value={offer.minimum_order_quantity} onValueChange={(value) => onUpdate(offerIndex, 'minimum_order_quantity', value)} disabled={readOnly} />
        <NumberField label="Lieferzeit (Tage)" min={0} max={3650} step={1} value={offer.lead_time_days ?? ''} onValueChange={(value) => onUpdate(offerIndex, 'lead_time_days', integerOrNull(value))} disabled={readOnly} />
        <NumberField label="Nettopreis" min={0} step="any" value={offer.net_price} onValueChange={(value) => onUpdate(offerIndex, 'net_price', value)} disabled={readOnly} />
        <NumberField label="Bruttopreis" min={0} step="any" value={offer.gross_price} onValueChange={(value) => onUpdate(offerIndex, 'gross_price', value)} disabled={readOnly} />
        <Checkbox label="Aktiv" checked={offer.is_active} onCheckedChange={(checked) => onUpdate(offerIndex, 'is_active', checked)} disabled={readOnly} />
      </div>
    </section>
  );
}

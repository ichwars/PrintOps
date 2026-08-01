import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type ReactNode } from 'react';

import { api } from '../../api/client';
import {
  procurementOffersApi,
  suppliersApi,
  type ProcurementOfferDraft,
} from '../../api/procurement';
import {
  smallPartsApi,
  type SmallPart,
  type SmallPartCreateInput,
  type SmallPartInput,
} from '../../api/smallParts';
import { Button, Checkbox, Modal, NumberField, Select, TextArea, TextField } from '../ui';
import { ProcurementOffersEditor } from './ProcurementOffersEditor';

interface SmallPartEditorProps {
  part: SmallPart | null;
  onClose: () => void;
}

const SUPPLIER_PAGE_SIZE = 50;

async function loadAllSuppliers() {
  const items = [];
  let offset = 0;
  while (true) {
    const page = await suppliersApi.list({ limit: SUPPLIER_PAGE_SIZE, offset });
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) return items;
    offset = page.offset + page.items.length;
  }
}

function FormSection({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section className="space-y-4" aria-labelledby={id}>
      <div className="flex items-center gap-3">
        <h3 id={id} className="shrink-0 text-sm font-semibold text-white">{title}</h3>
        <div className="h-px flex-1 bg-bambu-dark-tertiary" />
      </div>
      {children}
    </section>
  );
}

function formatQuantity(value: string | number | null | undefined, decimalPlaces: number): string {
  const parsed = Number(value ?? 0);
  if (!Number.isFinite(parsed)) return '0';
  const normalized = Math.max(0, parsed);
  if (decimalPlaces <= 0) return String(Math.round(normalized));
  return normalized.toFixed(decimalPlaces).replace(/\.?0+$/, '');
}

function formatMoney(value: string | number | null | undefined): string {
  const parsed = Number(value ?? 0);
  if (!Number.isFinite(parsed)) return '0.00';
  return Math.max(0, parsed).toFixed(2);
}

const initialForm = (part: SmallPart | null): SmallPartInput => ({
  sku: part?.sku ?? '',
  name: part?.name ?? '',
  description: part?.description ?? '',
  search_terms: part?.search_terms ?? '',
  category_id: part?.category_id ?? null,
  unit_code: part?.unit_code ?? '',
  location_id: part?.location_id ?? null,
  minimum_stock: formatQuantity(part?.minimum_stock, part?.unit.decimal_places ?? 0),
  unit_cost: formatMoney(part?.unit_cost),
  supplier_reference: part?.supplier_reference ?? null,
  default_consumption_reason: part?.default_consumption_reason ?? 'Produktion',
  internal_notes: part?.internal_notes ?? '',
  is_active: part?.is_active ?? true,
});

export function SmallPartEditor({ part, onClose }: SmallPartEditorProps) {
  const queryClient = useQueryClient();
  const categories = useQuery({ queryKey: ['small-parts', 'categories'], queryFn: smallPartsApi.categories.list });
  const units = useQuery({ queryKey: ['small-parts', 'units'], queryFn: smallPartsApi.units.list });
  const locations = useQuery({ queryKey: ['warehouse', 'locations'], queryFn: api.getLocations });
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings });
  const suppliers = useQuery({
    queryKey: ['suppliers', 'material-editor', 'all'],
    queryFn: loadAllSuppliers,
  });
  const offersQuery = useQuery({
    queryKey: ['procurement-offers', 'material', part?.id],
    queryFn: () => procurementOffersApi.list({ kind: 'material', small_part_id: part!.id }),
    enabled: part !== null,
  });
  const [form, setForm] = useState<SmallPartInput>(() => initialForm(part));
  const [openingQuantity, setOpeningQuantity] = useState('0');
  const [offers, setOffers] = useState<ProcurementOfferDraft[]>([]);
  const [minimumStockTouched, setMinimumStockTouched] = useState(false);
  const [error, setError] = useState('');
  const createdPartId = useRef<number | null>(null);
  const loadedOffersFor = useRef<number | null>(null);
  const selectedUnit = units.data?.find((unit) => unit.code === form.unit_code) ?? part?.unit ?? null;
  const quantityDecimals = selectedUnit?.decimal_places ?? 0;
  const quantityStep = quantityDecimals > 0 ? String(1 / (10 ** quantityDecimals)) : '1';

  useEffect(() => {
    if (part || minimumStockTouched || settings.data?.small_parts_default_minimum_stock == null) return;
    setForm((current) => ({
      ...current,
      minimum_stock: formatQuantity(settings.data?.small_parts_default_minimum_stock, quantityDecimals),
    }));
  }, [minimumStockTouched, part, quantityDecimals, settings.data?.small_parts_default_minimum_stock]);

  useEffect(() => {
    if (!part || !offersQuery.data || loadedOffersFor.current === part.id) return;
    setOffers(offersQuery.data);
    loadedOffersFor.current = part.id;
  }, [offersQuery.data, part]);

  const mutation = useMutation({
    mutationFn: async () => {
      let materialId = part?.id ?? createdPartId.current;
      if (materialId === null) {
        const createInput: SmallPartCreateInput = { ...form, opening_quantity: openingQuantity };
        const created = await smallPartsApi.create(createInput);
        materialId = created.id;
        createdPartId.current = created.id;
        setForm((current) => ({ ...current, sku: created.sku }));
      } else {
        await smallPartsApi.update(materialId, form);
      }
      const offersReady = !part || offersQuery.isSuccess;
      if (suppliers.isSuccess && offersReady) {
        await procurementOffersApi.replace({ kind: 'material', small_part_id: materialId }, offers);
      }
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['small-parts'] }),
        queryClient.invalidateQueries({ queryKey: ['procurement-offers'] }),
      ]);
      onClose();
    },
    onError: (caught) => setError(caught instanceof Error ? caught.message : 'Speichern fehlgeschlagen'),
  });

  const update = <K extends keyof SmallPartInput>(key: K, value: SmallPartInput[K]) =>
    setForm((current) => ({ ...current, [key]: value }));
  const updateUnit = (unitCode: string) => {
    const decimalPlaces = units.data?.find((unit) => unit.code === unitCode)?.decimal_places ?? 0;
    setOpeningQuantity((current) => formatQuantity(current, decimalPlaces));
    setForm((current) => ({
      ...current,
      unit_code: unitCode,
      minimum_stock: formatQuantity(current.minimum_stock, decimalPlaces),
    }));
  };
  return (
    <Modal
      open
      onClose={onClose}
      title={part ? 'Material bearbeiten' : 'Material hinzufügen'}
      closeLabel="Schließen"
      closeDisabled={mutation.isPending}
      className="max-w-3xl"
    >
      <form
        className="space-y-6"
        onSubmit={(event) => {
          event.preventDefault();
          setError('');
          mutation.mutate();
        }}
      >
        <FormSection id="material-section-article" title="Artikel">
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              label="Artikelnummer"
              required={!!part}
              value={form.sku}
              onValueChange={(value) => update('sku', value)}
              placeholder={part ? undefined : 'Wird aus Nummernkreis vergeben'}
              helperText={part ? undefined : 'Leer lassen für automatische Vergabe.'}
            />
            <TextField label="Bezeichnung" required value={form.name} onValueChange={(value) => update('name', value)} />
            <Select label="Kategorie" value={String(form.category_id ?? '')} onValueChange={(value) => update('category_id', value ? Number(value) : null)} options={[{ value: '', label: 'Keine Kategorie' }, ...(categories.data?.filter((item) => item.is_active).map((item) => ({ value: String(item.id), label: item.name })) ?? [])]} />
            <TextField label="Suchbegriffe" value={form.search_terms ?? ''} onValueChange={(value) => update('search_terms', value)} />
            {part ? <Checkbox className="sm:self-end sm:pb-2" checked={form.is_active} onCheckedChange={(checked) => update('is_active', checked)} label="Aktiv" /> : null}
            <div className="sm:col-span-2">
              <TextArea label="Beschreibung" value={form.description ?? ''} onValueChange={(value) => update('description', value)} className="min-h-20" />
            </div>
          </div>
        </FormSection>

        <FormSection id="material-section-stock" title="Bestand">
          <div className="grid gap-4 sm:grid-cols-2">
            {!part ? <NumberField label="Anfangsmenge" min="0" step={quantityStep} value={openingQuantity} onValueChange={(value) => setOpeningQuantity(value)} onBlur={() => setOpeningQuantity(formatQuantity(openingQuantity, quantityDecimals))} /> : null}
            <NumberField label="Mindestbestand" min="0" step={quantityStep} value={form.minimum_stock} onValueChange={(value) => { setMinimumStockTouched(true); update('minimum_stock', value); }} onBlur={() => update('minimum_stock', formatQuantity(form.minimum_stock, quantityDecimals))} />
            <Select label="Einheit" required value={form.unit_code} onValueChange={updateUnit} options={[{ value: '', label: 'Einheit auswählen' }, ...(units.data?.filter((item) => item.is_active).map((item) => ({ value: item.code, label: item.label })) ?? [])]} />
            <Select label="Lagerort" value={String(form.location_id ?? '')} onValueChange={(value) => update('location_id', value ? Number(value) : null)} options={[{ value: '', label: 'Kein Lagerort' }, ...(locations.data?.map((item) => ({ value: String(item.id), label: item.name })) ?? [])]} />
          </div>
        </FormSection>

        <FormSection id="material-section-procurement" title="Beschaffung">
          <div className="grid gap-4 sm:grid-cols-2">
            <NumberField
              label="Einzelpreis €"
              min="0"
              step="0.01"
              value={form.unit_cost}
              onValueChange={(value) => update('unit_cost', value)}
              onBlur={() => update('unit_cost', formatMoney(form.unit_cost))}
            />
          </div>
          {part?.supplier_reference ? (
            <TextField
              label="Bisherige Lieferantenreferenz"
              value={part.supplier_reference}
              onValueChange={() => undefined}
              readOnly
              helperText="Bleibt erhalten, bis sie einer Bezugsquelle zugeordnet wurde."
            />
          ) : null}
          {offersQuery.isPending && part ? <p className="text-sm text-bambu-gray">Bezugsquellen werden geladen …</p> : null}
          {offersQuery.isError ? <p role="alert" className="text-sm text-red-400">Bezugsquellen konnten nicht geladen werden.</p> : null}
          {!part || offersQuery.isSuccess ? (
            <ProcurementOffersEditor
              suppliers={suppliers.data ?? []}
              offers={offers}
              onChange={setOffers}
              readOnly={!suppliers.isSuccess}
            />
          ) : null}
          {suppliers.isError ? (
            <div className="flex flex-wrap items-center gap-3">
              <p role="alert" className="text-sm text-red-400">Lieferanten konnten nicht geladen werden. Material kann weiterhin ohne Änderung der Bezugsquellen gespeichert werden.</p>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                loading={suppliers.isFetching}
                onClick={() => suppliers.refetch()}
              >
                Lieferanten erneut laden
              </Button>
            </div>
          ) : null}
        </FormSection>

        <FormSection id="material-section-consumption" title="Verbrauchsgrund">
          <TextField label="Standard-Verbrauchsgrund" required value={form.default_consumption_reason} onValueChange={(value) => update('default_consumption_reason', value)} />
        </FormSection>

        <FormSection id="material-section-notes" title="Notiz intern">
          <TextArea label="Interne Notiz" value={form.internal_notes ?? ''} onValueChange={(value) => update('internal_notes', value)} className="min-h-24" />
        </FormSection>

        {error ? <p role="alert" className="rounded-lg bg-red-950/40 px-3 py-2 text-sm text-red-300">{error}</p> : null}
        <div className="sticky bottom-0 flex justify-end gap-3 border-t border-bambu-dark-tertiary bg-bambu-dark-secondary pt-4">
          <Button type="button" variant="secondary" onClick={onClose} disabled={mutation.isPending}>Abbrechen</Button>
          <Button type="submit" loading={mutation.isPending}>Material speichern</Button>
        </div>
      </form>
    </Modal>
  );
}

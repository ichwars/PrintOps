import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { api } from '../../api/client';
import { smallPartsApi, type SmallPart, type SmallPartInput } from '../../api/smallParts';
import { Checkbox, Modal, NumberField, Select, TextField } from '../ui';

interface SmallPartEditorProps {
  part: SmallPart | null;
  onClose: () => void;
}

export function SmallPartEditor({ part, onClose }: SmallPartEditorProps) {
  const queryClient = useQueryClient();
  const categories = useQuery({ queryKey: ['small-parts', 'categories'], queryFn: smallPartsApi.categories.list });
  const units = useQuery({ queryKey: ['small-parts', 'units'], queryFn: smallPartsApi.units.list });
  const locations = useQuery({ queryKey: ['warehouse', 'locations'], queryFn: api.getLocations });
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings });
  const [form, setForm] = useState<SmallPartInput>({
    sku: part?.sku ?? '',
    name: part?.name ?? '',
    description: part?.description ?? '',
    search_terms: part?.search_terms ?? '',
    category_id: part?.category_id ?? null,
    unit_code: part?.unit_code ?? '',
    location_id: part?.location_id ?? null,
    minimum_stock: part?.minimum_stock ?? '0',
    unit_cost: part?.unit_cost ?? '0',
    supplier_reference: part?.supplier_reference ?? '',
    is_active: part?.is_active ?? true,
  });
  const [minimumStockTouched, setMinimumStockTouched] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (part || minimumStockTouched || settings.data?.small_parts_default_minimum_stock == null) return;
    setForm((current) => ({
      ...current,
      minimum_stock: String(settings.data?.small_parts_default_minimum_stock ?? '0'),
    }));
  }, [minimumStockTouched, part, settings.data?.small_parts_default_minimum_stock]);
  const mutation = useMutation({
    mutationFn: () => part ? smallPartsApi.update(part.id, form) : smallPartsApi.create(form),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['small-parts'] });
      onClose();
    },
    onError: (caught) => setError(caught instanceof Error ? caught.message : 'Speichern fehlgeschlagen'),
  });
  const update = <K extends keyof SmallPartInput>(key: K, value: SmallPartInput[K]) =>
    setForm((current) => ({ ...current, [key]: value }));
  const inputClass = 'w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-white';

  return (
    <Modal open onClose={onClose} title={part ? 'Kleinteil bearbeiten' : 'Kleinteil anlegen'} closeLabel="Schließen">
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
        <TextField label="Artikelnummer" required value={form.sku} onValueChange={(value) => update('sku', value)} className={inputClass} />
        <TextField label="Bezeichnung" required value={form.name} onValueChange={(value) => update('name', value)} className={inputClass} />
        <Select label="Kategorie" value={String(form.category_id ?? '')} onValueChange={(value) => update('category_id', value ? Number(value) : null)} options={[{ value: '', label: 'Keine Kategorie' }, ...(categories.data?.filter((item) => item.is_active).map((item) => ({ value: String(item.id), label: item.name })) ?? [])]} />
        <Select label="Einheit" required value={form.unit_code} onValueChange={(value) => update('unit_code', value)} options={[{ value: '', label: 'Einheit auswählen' }, ...(units.data?.filter((item) => item.is_active).map((item) => ({ value: item.code, label: item.label })) ?? [])]} />
        <Select label="Lagerort" value={String(form.location_id ?? '')} onValueChange={(value) => update('location_id', value ? Number(value) : null)} options={[{ value: '', label: 'Kein Lagerort' }, ...(locations.data?.map((item) => ({ value: String(item.id), label: item.name })) ?? [])]} />
        <NumberField label="Meldebestand" min="0" step="0.01" value={form.minimum_stock} onValueChange={(value) => { setMinimumStockTouched(true); update('minimum_stock', value); }} className={inputClass} />
        <NumberField label="Einzelpreis €" min="0" step="0.01" value={form.unit_cost} onValueChange={(value) => update('unit_cost', value)} className={inputClass} />
        <TextField label="Lieferantenreferenz" value={form.supplier_reference ?? ''} onValueChange={(value) => update('supplier_reference', value)} className={inputClass} />
        <TextField label="Suchbegriffe" value={form.search_terms ?? ''} onValueChange={(value) => update('search_terms', value)} className={`${inputClass} sm:col-span-2`} />
        <Checkbox checked={form.is_active} onCheckedChange={(checked) => update('is_active', checked)} label="Aktiv" className="sm:col-span-2" />
        {error && <p role="alert" className="text-sm text-red-300 sm:col-span-2">{error}</p>}
        <div className="flex justify-end gap-2 sm:col-span-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-gray-600 px-4 py-2 text-sm text-gray-200">Abbrechen</button>
          <button type="submit" disabled={mutation.isPending} className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Speichern</button>
        </div>
      </form>
    </Modal>
  );
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { api } from '../../api/client';
import { smallPartsApi, type SmallPart, type SmallPartInput } from '../../api/smallParts';
import { Modal } from '../ui/Modal';

interface SmallPartEditorProps {
  part: SmallPart | null;
  onClose: () => void;
}

export function SmallPartEditor({ part, onClose }: SmallPartEditorProps) {
  const queryClient = useQueryClient();
  const categories = useQuery({ queryKey: ['small-parts', 'categories'], queryFn: smallPartsApi.categories.list });
  const units = useQuery({ queryKey: ['small-parts', 'units'], queryFn: smallPartsApi.units.list });
  const locations = useQuery({ queryKey: ['warehouse', 'locations'], queryFn: api.getLocations });
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
  const [error, setError] = useState('');
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
        <label className="space-y-1 text-sm text-gray-300">
          <span>Artikelnummer</span>
          <input required value={form.sku} onChange={(event) => update('sku', event.target.value)} className={inputClass} />
        </label>
        <label className="space-y-1 text-sm text-gray-300">
          <span>Bezeichnung</span>
          <input required value={form.name} onChange={(event) => update('name', event.target.value)} className={inputClass} />
        </label>
        <label className="space-y-1 text-sm text-gray-300">
          <span>Kategorie</span>
          <select value={form.category_id ?? ''} onChange={(event) => update('category_id', event.target.value ? Number(event.target.value) : null)} className={inputClass}>
            <option value="">Keine Kategorie</option>
            {categories.data?.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <label className="space-y-1 text-sm text-gray-300">
          <span>Einheit</span>
          <select required value={form.unit_code} onChange={(event) => update('unit_code', event.target.value)} className={inputClass}>
            <option value="">Einheit auswählen</option>
            {units.data?.filter((item) => item.is_active).map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
          </select>
        </label>
        <label className="space-y-1 text-sm text-gray-300">
          <span>Lagerort</span>
          <select value={form.location_id ?? ''} onChange={(event) => update('location_id', event.target.value ? Number(event.target.value) : null)} className={inputClass}>
            <option value="">Kein Lagerort</option>
            {locations.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <label className="space-y-1 text-sm text-gray-300">
          <span>Meldebestand</span>
          <input type="number" min="0" step="any" value={form.minimum_stock} onChange={(event) => update('minimum_stock', event.target.value)} className={inputClass} />
        </label>
        <label className="space-y-1 text-sm text-gray-300">
          <span>Einzelpreis €</span>
          <input type="number" min="0" step="0.01" value={form.unit_cost} onChange={(event) => update('unit_cost', event.target.value)} className={inputClass} />
        </label>
        <label className="space-y-1 text-sm text-gray-300">
          <span>Lieferantenreferenz</span>
          <input value={form.supplier_reference ?? ''} onChange={(event) => update('supplier_reference', event.target.value)} className={inputClass} />
        </label>
        <label className="space-y-1 text-sm text-gray-300 sm:col-span-2">
          <span>Suchbegriffe</span>
          <input value={form.search_terms ?? ''} onChange={(event) => update('search_terms', event.target.value)} className={inputClass} />
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-300 sm:col-span-2">
          <input type="checkbox" checked={form.is_active} onChange={(event) => update('is_active', event.target.checked)} /> Aktiv
        </label>
        {error && <p role="alert" className="text-sm text-red-300 sm:col-span-2">{error}</p>}
        <div className="flex justify-end gap-2 sm:col-span-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-gray-600 px-4 py-2 text-sm text-gray-200">Abbrechen</button>
          <button type="submit" disabled={mutation.isPending} className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Speichern</button>
        </div>
      </form>
    </Modal>
  );
}

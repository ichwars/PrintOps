import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';

import { api } from '../../api/client';
import { smallPartsApi } from '../../api/smallParts';
import { Card, CardContent, CardHeader } from '../Card';
import { Checkbox, NumberField, TextField } from '../ui';

interface SmallPartsSettingsProps {
  defaultMinimumStock: string;
  lowStockWarning: boolean;
  onDefaultsChange: (values: { defaultMinimumStock: string; lowStockWarning: boolean }) => void;
}

export function SmallPartsSettings({ defaultMinimumStock, lowStockWarning, onDefaultsChange }: SmallPartsSettingsProps) {
  const client = useQueryClient();
  const [categoryName, setCategoryName] = useState('');
  const [unitCode, setUnitCode] = useState('');
  const [unitLabel, setUnitLabel] = useState('');
  const [unitDecimals, setUnitDecimals] = useState(0);
  const [locationName, setLocationName] = useState('');
  const categories = useQuery({ queryKey: ['small-parts', 'categories'], queryFn: smallPartsApi.categories.list });
  const units = useQuery({ queryKey: ['small-parts', 'units'], queryFn: smallPartsApi.units.list });
  const locations = useQuery({ queryKey: ['warehouse', 'locations'], queryFn: api.getLocations });
  const invalidate = (...keys: unknown[][]) => Promise.all(keys.map((key) => client.invalidateQueries({ queryKey: key })));
  const addCategory = useMutation({
    mutationFn: () => smallPartsApi.categories.create({ name: categoryName }),
    onSuccess: async () => { setCategoryName(''); await invalidate(['small-parts', 'categories']); },
  });
  const deleteCategory = useMutation({
    mutationFn: smallPartsApi.categories.remove,
    onSuccess: () => invalidate(['small-parts', 'categories']),
  });
  const addUnit = useMutation({
    mutationFn: () => smallPartsApi.units.create({ code: unitCode, label: unitLabel, decimal_places: unitDecimals }),
    onSuccess: async () => { setUnitCode(''); setUnitLabel(''); setUnitDecimals(0); await invalidate(['small-parts', 'units']); },
  });
  const deleteUnit = useMutation({ mutationFn: smallPartsApi.units.remove, onSuccess: () => invalidate(['small-parts', 'units']) });
  const addLocation = useMutation({
    mutationFn: () => api.createLocation({ name: locationName }),
    onSuccess: async () => { setLocationName(''); await invalidate(['warehouse', 'locations']); },
  });
  const deleteLocation = useMutation({ mutationFn: api.deleteLocation, onSuccess: () => invalidate(['warehouse', 'locations']) });
  const inputClass = 'rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 py-2 text-sm text-white placeholder:text-bambu-gray focus:border-bambu-green focus:outline-none focus:ring-2 focus:ring-bambu-green/30';
  const addButtonClass = 'shrink-0 rounded-lg bg-bambu-green p-2 text-white transition-colors hover:bg-bambu-green-light focus:outline-none focus:ring-2 focus:ring-bambu-green';
  const listItemClass = 'flex items-center justify-between rounded-lg border border-bambu-dark-tertiary px-3 py-2 text-sm text-bambu-gray-light';
  const deleteButtonClass = 'rounded p-1 text-red-300 transition-colors hover:bg-red-500/10 hover:text-red-200 focus:outline-none focus:ring-2 focus:ring-red-500/50';

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-white">Materialkataloge</h2>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader><h3 className="font-semibold text-white">Kategorien</h3></CardHeader>
          <CardContent className="space-y-3">
            <form className="flex items-end gap-2" onSubmit={(event) => { event.preventDefault(); addCategory.mutate(); }}>
              <div className="min-w-0 flex-1 space-y-1">
                <p className="text-sm text-bambu-gray-light">Bezeichnung der Materialkategorie</p>
                <TextField aria-label="Neue Kategorie" required value={categoryName} onValueChange={setCategoryName} className={inputClass} />
              </div>
              <button aria-label="Kategorie hinzufügen" className={addButtonClass}><Plus className="h-5 w-5" /></button>
            </form>
            {categories.data?.map((category) => (
              <div key={category.id} className={listItemClass}>
                <span>{category.name}</span>
                <button aria-label={`${category.name} löschen`} onClick={() => deleteCategory.mutate(category.id)} className={deleteButtonClass}><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><h3 className="font-semibold text-white">Einheiten</h3></CardHeader>
          <CardContent className="space-y-3">
            <form className="grid grid-cols-[1fr_2fr_auto_auto] items-end gap-2" onSubmit={(event) => { event.preventDefault(); addUnit.mutate(); }}>
              <div className="space-y-1">
                <p className="text-sm text-bambu-gray-light">Einheitencode, z. B. C62</p>
                <TextField aria-label="Einheit Code" placeholder="C62" required value={unitCode} onValueChange={setUnitCode} className={inputClass} />
              </div>
              <div className="space-y-1">
                <p className="text-sm text-bambu-gray-light">Anzeigename, z. B. Stück</p>
                <TextField aria-label="Einheit Bezeichnung" placeholder="Stück" required value={unitLabel} onValueChange={setUnitLabel} className={inputClass} />
              </div>
              <div className="space-y-1">
                <p className="text-sm text-bambu-gray-light">Nachkommastellen</p>
                <NumberField aria-label="Nachkommastellen" min="0" max="6" value={unitDecimals} onValueChange={(value) => setUnitDecimals(Number(value))} className={`${inputClass} w-20`} />
              </div>
              <button aria-label="Einheit hinzufügen" className={addButtonClass}><Plus className="h-5 w-5" /></button>
            </form>
            {units.data?.map((unit) => (
              <div key={unit.code} className={listItemClass}>
                <span>{unit.label} <span className="text-bambu-gray">({unit.code}, {unit.decimal_places} Stellen)</span></span>
                <button aria-label={`${unit.label} löschen`} onClick={() => deleteUnit.mutate(unit.code)} className={deleteButtonClass}><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><h3 className="font-semibold text-white">Lagerorte</h3></CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <p className="text-sm text-bambu-gray-light">Lagerorte gelten gemeinsam für Filament und Material.</p>
              <form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); addLocation.mutate(); }}>
                <TextField aria-label="Neuer Lagerort" required value={locationName} onValueChange={setLocationName} className={`${inputClass} min-w-0 flex-1`} />
                <button aria-label="Lagerort hinzufügen" className={addButtonClass}><Plus className="h-5 w-5" /></button>
              </form>
            </div>
            {locations.data?.map((location) => (
              <div key={location.id} className={listItemClass}>
                <span>{location.name}</span>
                <button aria-label={`${location.name} löschen`} onClick={() => deleteLocation.mutate(location.id)} className={deleteButtonClass}><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><h3 className="font-semibold text-white">Standardwerte</h3></CardHeader>
          <CardContent className="space-y-4">
            <NumberField label="Standard-Meldebestand" min="0" step="0.01" value={defaultMinimumStock} onValueChange={(value) => onDefaultsChange({ defaultMinimumStock: value, lowStockWarning })} className={`${inputClass} w-full`} />
            <Checkbox checked={lowStockWarning} onCheckedChange={(checked) => onDefaultsChange({ defaultMinimumStock, lowStockWarning: checked })} label="Warnung bei niedrigem Bestand" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

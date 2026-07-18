import { Image as ImageIcon } from 'lucide-react';

import type { CalculationProjectPlate } from '../../../api/calculations';
import { formatGrams, formatHours } from '../../../utils/calculationFormatting';

interface ProjectPlateGridProps {
  plates: CalculationProjectPlate[];
  selectedIds: Set<number>;
  focusedId: number | null;
  locale: string;
  onSelectionChange: (ids: Set<number>) => void;
  onFocusChange: (id: number) => void;
}

export function ProjectPlateGrid({ plates, selectedIds, focusedId, locale, onSelectionChange, onFocusChange }: ProjectPlateGridProps) {
  const de = locale.startsWith('de');
  const toggle = (id: number) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    onSelectionChange(next);
  };
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {plates.map((plate) => (
        <article key={plate.id} className={`overflow-hidden rounded-lg border ${focusedId === plate.id ? 'border-bambu-green' : selectedIds.has(plate.id) ? 'border-bambu-green/50' : 'border-bambu-dark-tertiary'} bg-bambu-dark`}>
          <div className="flex items-center justify-between px-3 py-2">
            <label className="flex items-center gap-2 text-sm font-medium text-white">
              <input type="checkbox" aria-label={de ? `${plate.name} auswählen` : `Select ${plate.name}`} checked={selectedIds.has(plate.id)} onChange={() => toggle(plate.id)} className="accent-green-500" />
              {plate.name}
            </label>
            <span className="text-xs text-bambu-gray">{plate.object_count} {de ? 'Teile' : 'parts'}</span>
          </div>
          <button type="button" aria-label={de ? `Details von ${plate.name} öffnen` : `Open details for ${plate.name}`} onClick={() => onFocusChange(plate.id)} className="block w-full text-left">
            <div className="flex aspect-[4/3] items-center justify-center bg-bambu-dark-secondary">
              {plate.thumbnail_url ? <img src={plate.thumbnail_url} alt="" className="h-full w-full object-contain" /> : <ImageIcon className="h-10 w-10 text-bambu-gray" />}
            </div>
            <div className="flex justify-between px-3 py-2 text-xs text-bambu-gray">
              <span>{formatGrams(plate.detected_grams ?? 0, locale)}</span>
              <span>{formatHours(plate.detected_hours ?? 0, locale)}</span>
            </div>
          </button>
        </article>
      ))}
    </div>
  );
}

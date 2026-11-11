import { Layers } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { PlateInfo } from './types';

export function SelectedPlatesSummary({ plates, selected }: { plates: PlateInfo[]; selected: Set<number> }) {
  const { t } = useTranslation();
  const summary = plates.filter((plate) => selected.has(plate.index)).map((plate) => {
    const label = t('queue.plateNumber', { index: plate.index });
    const name = plate.name?.trim();
    return name && name !== label ? `${label}: ${name}` : label;
  }).join(', ');
  if (!summary) return null;
  return (
    <p className="flex items-center gap-1.5 text-sm text-bambu-gray min-w-0" title={summary} data-testid="selected-plates-summary">
      <Layers className="w-4 h-4 flex-shrink-0" />
      <span className="truncate">{summary}</span>
    </p>
  );
}

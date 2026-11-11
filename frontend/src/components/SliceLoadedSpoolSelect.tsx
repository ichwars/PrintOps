import { useTranslation } from 'react-i18next';
import type { LoadedSpoolPrinter, LoadedSpoolTray } from '../api/client';
import { formatSlotLabel, isAmsHtUnit } from '../utils/amsHelpers';
import { isLoaded, trayColourHex, type SlotMatch } from '../utils/sliceLoadedSpools';
import { LegacySelect } from './ui';

export interface SliceSpoolOption {
  tray: LoadedSpoolTray;
  match: SlotMatch | null;
}

export interface SliceSpoolGroup {
  printer: LoadedSpoolPrinter;
  spools: SliceSpoolOption[];
}

interface SliceLoadedSpoolSelectProps {
  slotLabel: string;
  groups: SliceSpoolGroup[];
  disabled: boolean;
  onPick: (match: SlotMatch, colour: string | null) => void;
}

function spoolKey(printerId: number, tray: LoadedSpoolTray): string {
  return `${printerId}:${tray.ams_id}:${tray.tray_id}`;
}

export function SliceLoadedSpoolSelect({ slotLabel, groups, disabled, onPick }: SliceLoadedSpoolSelectProps) {
  const { t } = useTranslation();

  const trayLabel = (printer: LoadedSpoolPrinter, tray: LoadedSpoolTray) => {
    if (tray.ams_id !== 255) return formatSlotLabel(tray.ams_id, tray.tray_id, isAmsHtUnit(tray.ams_id), false);
    if (printer.external_holders < 2) return t('printers.ext');
    return t(tray.tray_id === 0 ? 'printers.extL' : 'printers.extR');
  };

  if (!groups.some(({ spools }) => spools.some(({ tray }) => isLoaded(tray)))) return null;

  return (
    <LegacySelect
      aria-label={`${slotLabel} · ${t('slice.loadedSpools.choose')}`}
      value=""
      disabled={disabled}
      className="mt-1 w-full rounded-md border border-bambu-dark-tertiary bg-bambu-dark px-2 py-1 text-xs text-bambu-gray"
      onChange={(event) => {
        const key = event.target.value;
        for (const { printer, spools } of groups) {
          const picked = spools.find(({ tray }) => spoolKey(printer.id, tray) === key);
          if (picked?.match) {
            onPick(picked.match, trayColourHex(picked.tray));
            break;
          }
        }
      }}
    >
      <option value="">{t('slice.loadedSpools.choose')}</option>
      {groups.map(({ printer, spools }) => spools.length > 0 && (
        <optgroup key={printer.id} label={printer.name}>
          {spools.map(({ tray, match }) => {
            const key = spoolKey(printer.id, tray);
            const name = match?.preset.name ?? tray.tray_sub_brands ?? tray.tray_type;
            const description = match ? name : name
              ? `${name} · ${t('slice.loadedSpools.noProfile')}`
              : t('slice.loadedSpools.unidentified');
            return <option key={key} value={key} disabled={!match}>{trayLabel(printer, tray)} · {description}</option>;
          })}
        </optgroup>
      ))}
    </LegacySelect>
  );
}

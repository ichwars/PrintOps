import type { PrintQueueItem, PrinterStatus } from '../api/client';
import { formatSlotLabel, isAmsHtUnit } from '../utils/amsHelpers';

interface QueueFilamentNotesProps {
  item: PrintQueueItem;
  printerStatus?: PrinterStatus;
  t: (key: string, options?: Record<string, unknown>) => string;
}

function trayLabel(tray: number, status: PrinterStatus, t: QueueFilamentNotesProps['t']): string {
  if (tray >= 254) {
    const twoHolders = status.vt_tray?.some((holder) => holder.id === 255);
    if (!twoHolders) return t('printers.ext');
    return t(tray === 254 ? 'printers.extL' : 'printers.extR');
  }
  if (isAmsHtUnit(tray)) return formatSlotLabel(tray, 0, true, false);
  return formatSlotLabel(Math.floor(tray / 4), tray % 4, false, false);
}

export function QueueFilamentNotes({ item, printerStatus, t }: QueueFilamentNotesProps) {
  const colors = item.color_substitutions ?? [];
  const activeRun = item.status === 'printing' && printerStatus?.connected
    && item.archive_id != null && printerStatus.current_archive_id === item.archive_id
    && (item.plate_id == null || item.plate_id === printerStatus.current_plate_id);
  const backups = activeRun ? Object.entries(printerStatus.current_backup_trays ?? {}).filter(
    ([source]) => item.ams_mapping?.includes(Number(source)),
  ) : [];
  if (colors.length === 0 && backups.length === 0) return null;

  return (
    <ul className="mt-1 space-y-0.5 text-xs text-amber-700 dark:text-amber-300">
      {colors.map(({ slot_id: slot, wanted, got }) => (
        <li className="flex items-center gap-1.5" key={slot}>
          <span aria-hidden className="h-2.5 w-2.5 shrink-0 rounded-full border border-current" style={{ backgroundColor: wanted }} />
          <span aria-hidden className="h-2.5 w-2.5 shrink-0 rounded-full border border-current" style={{ backgroundColor: got }} />
          <span>{t('queue.filamentNotes.color', { slot, wanted, got })}</span>
        </li>
      ))}
      {printerStatus && backups.map(([source, target]) => (
        <li key={source}>{t('queue.filamentNotes.backup', {
          from: trayLabel(Number(source), printerStatus, t),
          to: trayLabel(target, printerStatus, t),
        })}</li>
      ))}
    </ul>
  );
}

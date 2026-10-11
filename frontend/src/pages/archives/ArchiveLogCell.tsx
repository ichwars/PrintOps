import { api } from '../../api/client';
import type { PrintLogEntry } from '../../api/client';
import { formatDateTime, formatDuration, type TimeFormat } from '../../utils/date';

type Props = {
  colId: string;
  entry: PrintLogEntry;
  currency: string;
  timeFormat: TimeFormat;
  t: (key: string, options?: Record<string, unknown>) => string;
};

export function ArchiveLogCell({ colId, entry, currency, timeFormat, t }: Props) {
  switch (colId) {
    case 'date':
      return (
        <span className="text-white whitespace-nowrap">
          {formatDateTime(entry.started_at || entry.created_at, timeFormat)}
        </span>
      );
    case 'completed_at':
      return (
        <span className="text-bambu-gray-light whitespace-nowrap">
          {entry.completed_at ? formatDateTime(entry.completed_at, timeFormat) : '—'}
        </span>
      );
    case 'print_name':
      return (
        <div className="flex items-center gap-2">
          {entry.thumbnail_path && (
            <img
              src={api.getPrintLogThumbnail(entry.id)}
              alt=""
              className="w-8 h-8 rounded object-cover flex-shrink-0"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
          )}
          <span className="text-white break-words" title={entry.print_name || ''}>
            {entry.print_name || '—'}
          </span>
        </div>
      );
    case 'printer':
      return <span className="text-bambu-gray-light">{entry.printer_name || '—'}</span>;
    case 'user':
      return <span className="text-bambu-gray-light">{entry.created_by_username || '—'}</span>;
    case 'status':
      return (
        <>
          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
            entry.status === 'completed' ? 'bg-green-100 dark:bg-green-500/20 text-green-700 dark:text-green-400' :
            entry.status === 'failed' ? 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400' :
            entry.status === 'stopped' ? 'bg-yellow-100 dark:bg-yellow-500/20 text-yellow-700 dark:text-yellow-400' :
            entry.status === 'cancelled' ? 'bg-orange-100 dark:bg-orange-500/20 text-orange-700 dark:text-orange-400' :
            entry.status === 'skipped' ? 'bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-400' :
            'bg-gray-500/20 text-gray-400'
          }`}>
            {entry.status}
          </span>
          {entry.failure_reason && (
            <span className="block text-[10px] text-bambu-gray mt-0.5">
              {t(`editArchive.failureReasons.${entry.failure_reason}`, { defaultValue: entry.failure_reason })}
            </span>
          )}
        </>
      );
    case 'duration':
      return (
        <span className="text-bambu-gray-light whitespace-nowrap">
          {entry.duration_seconds ? formatDuration(entry.duration_seconds) : '—'}
        </span>
      );
    case 'filament':
      return (
        <div className="flex items-center gap-1.5">
          {entry.filament_color && (
            <div className="flex items-center gap-0.5 flex-wrap">
              {entry.filament_color.split(',').map((color, i) => {
                const trimmed = color.trim();
                return (
                  <span
                    key={i}
                    className="w-3 h-3 rounded-full border border-black/20 flex-shrink-0"
                    style={{ backgroundColor: trimmed.startsWith('#') ? trimmed : undefined }}
                    title={trimmed}
                  />
                );
              })}
            </div>
          )}
          <span className="text-bambu-gray-light text-xs">
            {entry.filament_type || '—'}
          </span>
        </div>
      );
    case 'filament_used':
      // Per-run actual, not the archive's estimate: partial prints are
      // scaled to progress and multi-plate archives are scoped to the
      // plate that printed. One decimal matches the per-archive log table.
      return (
        <span className="text-bambu-gray-light whitespace-nowrap tabular-nums">
          {entry.filament_used_grams != null ? `${entry.filament_used_grams.toFixed(1)} g` : '—'}
        </span>
      );
    case 'cost':
      return (
        <span className="text-bambu-gray-light whitespace-nowrap tabular-nums">
          {entry.cost != null ? `${currency}${entry.cost.toFixed(2)}` : '—'}
        </span>
      );
    case 'energy':
      // Written by the energy background task after the row itself, so a
      // just-finished print shows "—" for a moment. That is accurate: the
      // measurement genuinely isn't in yet.
      return (
        <span className="text-bambu-gray-light whitespace-nowrap tabular-nums">
          {entry.energy_kwh != null ? `${entry.energy_kwh.toFixed(2)} kWh` : '—'}
        </span>
      );
    case 'energy_cost':
      return (
        <span className="text-bambu-gray-light whitespace-nowrap tabular-nums">
          {entry.energy_cost != null ? `${currency}${entry.energy_cost.toFixed(2)}` : '—'}
        </span>
      );
    default:
      return null;
  }
}

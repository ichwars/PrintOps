export const LOG_COLUMN_CONFIG_KEY = 'printops-printlog-columns';

/** Column id -> i18n key. Also the authoritative list of valid ids. */
export const LOG_COLUMN_LABEL_KEYS: Record<string, string> = {
  date: 'archives.log.date',
  print_name: 'archives.log.printName',
  printer: 'archives.log.printer',
  user: 'archives.log.user',
  status: 'archives.log.status',
  duration: 'archives.log.duration',
  completed_at: 'archives.log.completedAt',
  filament: 'archives.log.filament',
  filament_used: 'archives.log.filamentUsed',
  cost: 'archives.log.cost',
  energy: 'archives.log.energy',
  energy_cost: 'archives.log.energyCost',
};

// Defaults reproduce the previous seven columns in the same order, plus the
// filament amount the issue actually asked for. The rest ship hidden: they are
// available to anyone who wants them without widening the table for everyone
// who doesn't.
export const DEFAULT_LOG_COLUMNS: Array<{ id: string; visible: boolean }> = [
  { id: 'date', visible: true },
  { id: 'print_name', visible: true },
  { id: 'printer', visible: true },
  { id: 'user', visible: true },
  { id: 'status', visible: true },
  { id: 'duration', visible: true },
  { id: 'filament', visible: true },
  { id: 'filament_used', visible: true },
  { id: 'completed_at', visible: false },
  { id: 'cost', visible: false },
  { id: 'energy', visible: false },
  { id: 'energy_cost', visible: false },
];

/** Stored config merged with the defaults: unknown ids (removed columns) are
 *  dropped and ids added by a later Bambuddy version are appended with their
 *  default visibility, so an upgrade never silently hides a new column or
 *  crashes on one that no longer exists. */
export function loadLogColumnConfig(): Array<{ id: string; visible: boolean }> {
  try {
    const stored = localStorage.getItem(LOG_COLUMN_CONFIG_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as Array<{ id: string; visible: boolean }>;
      const known = new Set(Object.keys(LOG_COLUMN_LABEL_KEYS));
      const storedIds = new Set(parsed.map((c) => c.id));
      const valid = parsed
        .filter((c) => known.has(c.id))
        .map((c) => ({ id: c.id, visible: !!c.visible }));
      const added = DEFAULT_LOG_COLUMNS.filter((c) => !storedIds.has(c.id));
      if (valid.length > 0) return [...valid, ...added];
    }
  } catch {
    // Corrupt or unavailable storage falls back to defaults.
  }
  return DEFAULT_LOG_COLUMNS.map((c) => ({ ...c }));
}

export const LOG_SORT_KEY = 'printops-printlog-sort';

export type LogSortState = { column: string; direction: 'asc' | 'desc' };

/** Column ids the backend will order by. Kept in step with
 *  ``_SORTABLE_COLUMNS`` in ``routes/print_log.py`` — an id missing there
 *  comes back as a 400, so a header is only made clickable if it is listed
 *  in both. */
export const SORTABLE_LOG_COLUMNS = new Set(Object.keys(LOG_COLUMN_LABEL_KEYS));

export const DEFAULT_LOG_SORT: LogSortState = { column: 'date', direction: 'desc' };

export function loadLogSort(): LogSortState {
  try {
    const stored = localStorage.getItem(LOG_SORT_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as LogSortState;
      if (SORTABLE_LOG_COLUMNS.has(parsed?.column) && (parsed.direction === 'asc' || parsed.direction === 'desc')) {
        return parsed;
      }
    }
  } catch {
    // Fall through to the default.
  }
  return { ...DEFAULT_LOG_SORT };
}

export function saveLogSort(state: LogSortState) {
  try {
    localStorage.setItem(LOG_SORT_KEY, JSON.stringify(state));
  } catch {
    // Private-mode / quota failures shouldn't break the page.
  }
}

export function saveLogColumnConfig(config: Array<{ id: string; visible: boolean }>) {
  try {
    localStorage.setItem(
      LOG_COLUMN_CONFIG_KEY,
      JSON.stringify(config.map((c) => ({ id: c.id, visible: c.visible }))),
    );
  } catch {
    // Private-mode / quota failures shouldn't break the page.
  }
}

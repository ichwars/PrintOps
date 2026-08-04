import type { HMSError } from '../../api/client';
import { type PrinterState } from '../../components/BulkPrinterToolbar';
import { filterKnownHMSErrors } from '../../components/HMSErrorModal';

export const STATUS_GROUP_ORDER: string[] = ['error', 'printing', 'paused', 'finished', 'idle', 'offline'];

export const STATUS_GROUP_META: Record<string, { labelKey: string; dot: string }> = {
  error:    { labelKey: 'printers.status.problem',   dot: 'bg-status-error' },
  printing: { labelKey: 'printers.status.printing',  dot: 'bg-bambu-green animate-pulse' },
  paused:   { labelKey: 'printers.status.paused',    dot: 'bg-status-warning' },
  finished: { labelKey: 'printers.status.finished',  dot: 'bg-blue-400' },
  idle:     { labelKey: 'printers.status.idle',       dot: 'bg-bambu-green' },
  offline:  { labelKey: 'printers.status.offline',   dot: 'bg-gray-400' },
};

/** Classify a printer into one of the UI status buckets. */
export function classifyPrinterStatus(
  status: { connected: boolean; state: string | null; hms_errors?: HMSError[] } | undefined,
): PrinterState {
  if (!status?.connected) return 'offline';
  const hmsErrors = status.hms_errors ? filterKnownHMSErrors(status.hms_errors) : [];
  if (hmsErrors.length > 0) return 'error';
  switch (status.state) {
    case 'RUNNING': return 'printing';
    case 'PAUSE':   return 'paused';
    case 'FINISH':  return 'finished';
    // FAILED without an active HMS error is the printer's terminal state after
    // any unsuccessful end — including user-cancellations. Treat the same as
    // FINISH for grouping/badging purposes; only escalate to "error" when an
    // HMS code is actually attached (handled by the early-return above).
    case 'FAILED':  return 'finished';
    default:        return 'idle';
  }
}

/**
 * Get human-readable status display text for a printer.
 * Uses stg_cur_name for detailed calibration/preparation stages,
 * otherwise formats the gcode_state nicely.
 */
export function getStatusDisplay(state: string | null | undefined, stg_cur_name: string | null | undefined): string {
  // If we have a specific stage name (calibration, heating, etc.), use it
  if (stg_cur_name) {
    return stg_cur_name;
  }

  // Format the gcode_state nicely
  switch (state) {
    case 'RUNNING':
      return 'Printing';
    case 'PAUSE':
      return 'Paused';
    case 'FINISH':
      return 'Finished';
    case 'FAILED':
      return 'Failed';
    case 'IDLE':
      return 'Idle';
    default:
      return state ? state.charAt(0) + state.slice(1).toLowerCase() : 'Idle';
  }
}

// Bambu models that ship with an enclosure chamber fan (firmware field
// `big_fan2_speed`). Open-frame models (A1 / A1 Mini / A2L / P1P) have no
// chamber fan — `big_fan2_speed` is meaningless / always 0 there, so the
// widget is hidden in fanItems instead of rendered greyed-out.
export const MODELS_WITH_CHAMBER_FAN: ReadonlySet<string> = new Set([
  'X1C',
  'X1',
  'X1E',
  'X2D',
  'P1S',
  'P2S',
  'H2D',
  'H2D Pro',
  'H2C',
  'H2S',
]);

// Map SSDP model codes to display names
export function mapModelCode(ssdpModel: string | null): string {
  if (!ssdpModel) return '';
  const modelMap: Record<string, string> = {
    // H2 Series
    'O1D': 'H2D',
    'O1E': 'H2D Pro',
    'O2D': 'H2D Pro',
    'O1C': 'H2C',
    'O1C2': 'H2C',
    'O1S': 'H2S',
    // X1 Series
    'BL-P001': 'X1C',
    'BL-P002': 'X1',
    'BL-P003': 'X1E',
    // X2 Series
    'N6': 'X2D',
    // A2 Series
    'N9': 'A2L',
    // P Series
    'C11': 'P1S',
    'C12': 'P1P',
    'C13': 'P2S',
    // A1 Series
    'N2S': 'A1',
    'N1': 'A1 Mini',
    // Direct matches
    'X1C': 'X1C',
    'X1': 'X1',
    'X1E': 'X1E',
    'X2D': 'X2D',
    'P1S': 'P1S',
    'P1P': 'P1P',
    'P2S': 'P2S',
    'A1': 'A1',
    'A1 Mini': 'A1 Mini',
    'A2L': 'A2L',
    'H2D': 'H2D',
    'H2D Pro': 'H2D Pro',
    'H2C': 'H2C',
    'H2S': 'H2S',
  };
  return modelMap[ssdpModel] || ssdpModel;
}

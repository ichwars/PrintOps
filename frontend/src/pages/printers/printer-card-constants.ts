// The estimated height intentionally errs high so the popover flips before it clips.
export const DRYING_POPOVER_WIDTH = 240;
export const DRYING_POPOVER_ESTIMATED_HEIGHT = 320;
export const DRY_START_CONFIRM_MS = 30_000;

export const DRYING_PRESETS: Record<
  string,
  { n3f: number; n3s: number; n3f_hours: number; n3s_hours: number }
> = {
  PLA: { n3f: 45, n3s: 45, n3f_hours: 12, n3s_hours: 12 },
  PETG: { n3f: 65, n3s: 65, n3f_hours: 12, n3s_hours: 12 },
  TPU: { n3f: 65, n3s: 75, n3f_hours: 12, n3s_hours: 18 },
  ABS: { n3f: 65, n3s: 80, n3f_hours: 12, n3s_hours: 8 },
  ASA: { n3f: 65, n3s: 80, n3f_hours: 12, n3s_hours: 8 },
  PA: { n3f: 65, n3s: 85, n3f_hours: 12, n3s_hours: 12 },
  PC: { n3f: 65, n3s: 80, n3f_hours: 12, n3s_hours: 8 },
  PVA: { n3f: 65, n3s: 85, n3f_hours: 12, n3s_hours: 18 },
};

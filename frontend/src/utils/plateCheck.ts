import type { TFunction } from 'i18next';

const failureReasons = new Set([
  'no_camera_frame',
  'decode_failed',
  'analysis_error',
  'opencv_missing',
  'not_calibrated',
]);

export function plateCheckFailureText(t: TFunction, reason: string | null | undefined): string {
  const key = reason && failureReasons.has(reason) ? reason : 'error';
  return t('printers.plateDetection.unavailableReasons.' + key);
}

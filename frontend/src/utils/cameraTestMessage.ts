import type { TFunction } from 'i18next';
import type { ExternalCameraTestResult } from '../api/client/printers-files';

export function cameraTestMessage(result: ExternalCameraTestResult, t: TFunction): string {
  if (!result.success) {
    if (result.live_view) return t('settings.toast.cameraLiveViewPending');
    return result.error || t('settings.toast.connectionFailed');
  }
  return t(result.live_view ? 'settings.toast.cameraConnectedLiveView' : 'settings.toast.cameraConnected', {
    resolution: result.resolution ? ` (${result.resolution})` : '',
  });
}

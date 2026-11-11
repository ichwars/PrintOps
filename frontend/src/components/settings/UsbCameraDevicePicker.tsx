import { useSyncExternalStore } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api, getAuthSessionId, subscribeAuthSession } from '../../api/client';
import { LegacySelect } from '../ui';

export function UsbCameraDevicePicker({ value, onSelect }: { value: string; onSelect: (device: string) => void }) {
  const { t } = useTranslation();
  const session = useSyncExternalStore(subscribeAuthSession, getAuthSessionId);
  const cameras = useQuery({ queryKey: ['usb-cameras', session], queryFn: api.listUsbCameras, retry: false });
  const discovered = cameras.data?.cameras ?? [];
  const selected = discovered.some((camera) => camera.device === value) ? value : '';
  return (
    <div className="w-full space-y-1">
      <div className="flex gap-2">
        <LegacySelect aria-label={t('settings.usbCameraChoose')} value={selected}
          disabled={discovered.length === 0} className="min-w-0 flex-1"
          onChange={(event) => { if (event.target.value) onSelect(event.target.value); }}>
          <option value="" disabled>{cameras.isPending ? t('common.loading') : t('settings.usbCameraChoose')}</option>
          {discovered.map((camera) => (
            <option key={camera.device} value={camera.device}>{camera.name} ({camera.device})</option>
          ))}
        </LegacySelect>
        <button type="button" aria-label={t('settings.usbCameraRefresh')} title={t('settings.usbCameraRefresh')}
          disabled={cameras.isFetching} onClick={() => void cameras.refetch()} className="rounded p-2 hover:bg-bambu-dark-tertiary">
          <RefreshCw className={`h-4 w-4 ${cameras.isFetching ? 'animate-spin' : ''}`} />
        </button>
      </div>
      {cameras.isError && <p role="alert" className="text-xs text-red-400">{t('settings.usbCameraListError')}</p>}
      {cameras.isSuccess && discovered.length === 0 && (
        <p role="status" className="text-xs text-bambu-gray">{t('settings.usbCameraNone')} <code>/dev/video0</code></p>
      )}
      {cameras.isSuccess && discovered.length > 0 && value && !selected && (
        <p role="status" className="text-xs text-bambu-gray">{t('settings.usbCameraMissing', { device: value })}</p>
      )}
    </div>
  );
}
